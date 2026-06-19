import os
import sys
import json
import time
import importlib.util
from time import gmtime, strftime
import torch.distributed as dist
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader
from torch.utils.data.distributed import DistributedSampler
from torch.nn.parallel import DistributedDataParallel as DDP

try:
    import comet_ml
except ImportError:  # pragma: no cover - optional dependency
    comet_ml = None

# Ensure project root is in path regardless of the current working directory.
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from config import Config
from dataset import QlibDataset
from model.kronos import KronosTokenizer
from tokenizer_safety import (
    is_cuda_oom_error,
    resolve_tokenizer_validation_batch_size,
    save_tokenizer_checkpoint,
    unwrap_model,
    write_tokenizer_validation_failure,
)
# Import shared utilities
from utils.training_utils import (
    setup_ddp,
    cleanup_ddp,
    set_seed,
    get_model_size,
    format_time,
)


def create_dataloaders(config: dict, rank: int, world_size: int):
    """
    Creates and returns distributed dataloaders for training and validation.

    Args:
        config (dict): A dictionary of configuration parameters.
        rank (int): The global rank of the current process.
        world_size (int): The total number of processes.

    Returns:
        tuple: A tuple containing (train_loader, val_loader, train_dataset, valid_dataset).
    """
    print(f"[Rank {rank}] Creating distributed dataloaders...")
    train_dataset = QlibDataset('train')
    valid_dataset = QlibDataset('val')
    print(f"[Rank {rank}] Train dataset size: {len(train_dataset)}, Validation dataset size: {len(valid_dataset)}")

    use_distributed_sampler = world_size > 1 and dist.is_available() and dist.is_initialized()
    train_sampler = (
        DistributedSampler(train_dataset, num_replicas=world_size, rank=rank, shuffle=True)
        if use_distributed_sampler
        else None
    )
    val_sampler = (
        DistributedSampler(valid_dataset, num_replicas=world_size, rank=rank, shuffle=False)
        if use_distributed_sampler
        else None
    )
    drop_last = config.get("dataset_sample_mode") != "full_sequential"

    # GPU 최대 활용: persistent_workers + prefetch_factor 는 num_workers > 0 일 때만 의미.
    n_workers = int(config.get('num_workers', 2) or 0)
    persistent = bool(config.get('persistent_workers', False)) and n_workers > 0
    loader_extra = {}
    if n_workers > 0:
        loader_extra['prefetch_factor'] = int(config.get('prefetch_factor', 2))
        loader_extra['persistent_workers'] = persistent

    train_loader = DataLoader(
        train_dataset,
        batch_size=config['batch_size'],
        sampler=train_sampler,
        shuffle=train_sampler is None and config.get("dataset_sample_mode") != "full_sequential",
        num_workers=n_workers,
        pin_memory=True,
        drop_last=drop_last,
        **loader_extra,
    )
    validation_batch_size = resolve_tokenizer_validation_batch_size(config)
    val_loader = DataLoader(
        valid_dataset,
        batch_size=validation_batch_size,
        sampler=val_sampler,
        shuffle=False,
        num_workers=n_workers,
        pin_memory=True,
        drop_last=False,
        **loader_extra,
    )
    print(
        f"[Rank {rank}] Dataloaders created. Train steps/epoch: {len(train_loader)}, "
        f"Val steps: {len(val_loader)}, Validation batch size: {validation_batch_size}"
    )
    return train_loader, val_loader, train_dataset, valid_dataset


def train_model(model, device, config, save_dir, logger, rank, world_size):
    """
    The main training and validation loop for the tokenizer.

    Args:
        model (DDP): The DDP-wrapped model to train.
        device (torch.device): The device for the current process.
        config (dict): Configuration dictionary.
        save_dir (str): Directory to save checkpoints.
        logger (comet_ml.Experiment): Comet logger instance.
        rank (int): Global rank of the process.
        world_size (int): Total number of processes.

    Returns:
        tuple: A tuple containing the trained model and a dictionary of results.
    """
    start_time = time.time()
    if rank == 0:
        effective_bs = config['batch_size'] * world_size * config['accumulation_steps']
        print(f"[Rank {rank}] BATCHSIZE (per GPU): {config['batch_size']}")
        print(f"[Rank {rank}] Effective total batch size: {effective_bs}")

    train_loader, val_loader, train_dataset, valid_dataset = create_dataloaders(config, rank, world_size)

    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=config['tokenizer_learning_rate'],
        weight_decay=config['adam_weight_decay']
    )

    scheduler = torch.optim.lr_scheduler.OneCycleLR(
        optimizer=optimizer,
        max_lr=config['tokenizer_learning_rate'],
        steps_per_epoch=len(train_loader),
        epochs=config['epochs'],
        pct_start=0.03,
        div_factor=10
    )

    best_val_loss = float('inf')
    dt_result = {}
    batch_idx_global_train = 0

    # ── AMP / autocast 설정 (opt-in) ────────────────────────────
    amp_enabled = bool(config.get('tokenizer_enable_amp', False)) and torch.cuda.is_available()
    amp_dtype_label = str(config.get('tokenizer_amp_dtype', 'bf16')).lower()
    if amp_dtype_label in ('bf16', 'bfloat16'):
        amp_dtype = torch.bfloat16
    elif amp_dtype_label in ('fp16', 'float16', 'half'):
        amp_dtype = torch.float16
    else:
        amp_enabled = False
        amp_dtype = torch.float32
    amp_use_scaler = amp_enabled and amp_dtype == torch.float16
    scaler = torch.amp.GradScaler('cuda', enabled=amp_use_scaler)
    if rank == 0 and amp_enabled:
        print(f"[Rank {rank}] AMP enabled - dtype={amp_dtype_label} scaler={amp_use_scaler}")

    def autocast_ctx():
        if not amp_enabled:
            from contextlib import nullcontext
            return nullcontext()
        return torch.amp.autocast('cuda', dtype=amp_dtype)

    for epoch_idx in range(config['epochs']):
        epoch_start_time = time.time()
        model.train()
        if hasattr(train_loader.sampler, "set_epoch"):
            train_loader.sampler.set_epoch(epoch_idx)

        # Set dataset seeds for reproducible sampling
        train_dataset.set_epoch_seed(epoch_idx * 10000 + rank)
        valid_dataset.set_epoch_seed(0)  # Keep validation sampling consistent

        for i, (ori_batch_x, _) in enumerate(train_loader):
            ori_batch_x = ori_batch_x.to(device, non_blocking=True)

            # --- Gradient Accumulation Loop ---
            current_batch_total_loss = 0.0
            for j in range(config['accumulation_steps']):
                start_idx = j * (ori_batch_x.shape[0] // config['accumulation_steps'])
                end_idx = (j + 1) * (ori_batch_x.shape[0] // config['accumulation_steps'])
                batch_x = ori_batch_x[start_idx:end_idx]

                # Forward + loss (AMP autocast 활성 시 bf16/fp16 로 자동 cast)
                with autocast_ctx():
                    zs, bsq_loss, _, _ = model(batch_x)
                    z_pre, z = zs
                    recon_loss_pre = F.mse_loss(z_pre, batch_x)
                    recon_loss_all = F.mse_loss(z, batch_x)
                    recon_loss = recon_loss_pre + recon_loss_all
                    loss = (recon_loss + bsq_loss) / 2  # Assuming w_1=w_2=1

                loss_scaled = loss / config['accumulation_steps']
                current_batch_total_loss += loss.item()
                # fp16 일 때만 GradScaler — bf16/fp32 에서는 일반 backward
                if amp_use_scaler:
                    scaler.scale(loss_scaled).backward()
                else:
                    loss_scaled.backward()

            # --- Optimizer Step after Accumulation ---
            if amp_use_scaler:
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=2.0)
                scaler.step(optimizer)
                scaler.update()
            else:
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=2.0)
                optimizer.step()
            scheduler.step()
            optimizer.zero_grad(set_to_none=True)

            # --- Logging (Master Process Only) ---
            if rank == 0 and (batch_idx_global_train + 1) % config['log_interval'] == 0:
                avg_loss = current_batch_total_loss / config['accumulation_steps']
                print(
                    f"[Rank {rank}, Epoch {epoch_idx + 1}/{config['epochs']}, Step {i + 1}/{len(train_loader)}] "
                    f"LR {optimizer.param_groups[0]['lr']:.6f}, Loss: {avg_loss:.4f}"
                )
            if rank == 0 and logger:
                avg_loss = current_batch_total_loss / config['accumulation_steps']
                logger.log_metric('train_tokenizer_loss_batch', avg_loss, step=batch_idx_global_train)
                logger.log_metric(f'train_vqvae_vq_loss_each_batch', bsq_loss.item(), step=batch_idx_global_train)
                logger.log_metric(f'train_recon_loss_pre_each_batch', recon_loss_pre.item(), step=batch_idx_global_train)
                logger.log_metric(f'train_recon_loss_each_batch', recon_loss_all.item(), step=batch_idx_global_train)
                logger.log_metric('tokenizer_learning_rate', optimizer.param_groups[0]["lr"], step=batch_idx_global_train)

            batch_idx_global_train += 1

        pre_validation_checkpoint = None
        if config.get("tokenizer_save_pre_validation_checkpoint", True):
            pre_validation_checkpoint = save_tokenizer_checkpoint(
                model,
                save_dir,
                str(config.get("tokenizer_pre_validation_checkpoint_name") or "latest_train_model"),
                rank,
                reason=f"pre-validation epoch {epoch_idx + 1}",
            )

        if dist.is_available() and dist.is_initialized():
            dist.barrier()

        try:
            del ori_batch_x, batch_x, zs, z_pre, z, loss, loss_scaled
            del bsq_loss, recon_loss_pre, recon_loss_all, recon_loss
        except UnboundLocalError:
            pass

        optimizer.zero_grad(set_to_none=True)
        if torch.cuda.is_available() and config.get("tokenizer_empty_cache_before_validation", True):
            torch.cuda.empty_cache()

        # --- Validation Loop ---
        model.eval()
        tot_val_loss_sum_rank = 0.0
        val_sample_count_rank = 0
        val_total_steps = len(val_loader)
        val_log_interval = max(1, int(config.get('tokenizer_validation_log_interval', config['log_interval']) or 1))
        val_max_steps = max(0, int(config.get('tokenizer_validation_max_steps', 0) or 0))
        if rank == 0:
            val_limit_label = val_max_steps if val_max_steps > 0 else "all"
            print(
                f"[Rank {rank}] Tokenizer validation started. "
                f"Steps: {val_total_steps}, Log interval: {val_log_interval}, Max steps: {val_limit_label}"
            )
        try:
            with torch.inference_mode():
                for val_step_idx, (ori_batch_x, _) in enumerate(val_loader, start=1):
                    ori_batch_x = ori_batch_x.to(device, non_blocking=True)
                    with autocast_ctx():
                        zs, _, _, _ = model(ori_batch_x)
                        _, z = zs
                        val_loss_item = F.mse_loss(z, ori_batch_x)

                    tot_val_loss_sum_rank += val_loss_item.item() * ori_batch_x.size(0)
                    val_sample_count_rank += ori_batch_x.size(0)
                    should_log_validation = (
                        val_step_idx == 1
                        or val_step_idx % val_log_interval == 0
                        or val_step_idx == val_total_steps
                        or (val_max_steps > 0 and val_step_idx >= val_max_steps)
                    )
                    if rank == 0 and should_log_validation:
                        running_val_loss = (
                            tot_val_loss_sum_rank / val_sample_count_rank
                            if val_sample_count_rank > 0
                            else 0.0
                        )
                        print(
                            f"[Rank {rank}] Tokenizer validation progress: "
                            f"Step {val_step_idx}/{val_total_steps}, Samples {val_sample_count_rank}, "
                            f"Loss: {running_val_loss:.4f}"
                        )
                    if val_max_steps > 0 and val_step_idx >= val_max_steps:
                        if rank == 0:
                            print(
                                f"[Rank {rank}] Tokenizer validation capped at "
                                f"{val_step_idx}/{val_total_steps} steps by KRONOS_TOKENIZER_VAL_MAX_STEPS."
                            )
                        break
        except Exception as exc:
            if torch.cuda.is_available() and is_cuda_oom_error(exc):
                torch.cuda.empty_cache()
                write_tokenizer_validation_failure(save_dir, epoch_idx, exc, pre_validation_checkpoint, rank)
                if rank == 0:
                    print(
                        "Tokenizer validation failed with CUDA OOM. "
                        f"Pre-validation checkpoint remains at {pre_validation_checkpoint}."
                    )
            raise

        if dist.is_available() and dist.is_initialized():
            val_loss_sum_tensor = torch.tensor(tot_val_loss_sum_rank, device=device)
            val_count_tensor = torch.tensor(val_sample_count_rank, device=device)
            dist.all_reduce(val_loss_sum_tensor, op=dist.ReduceOp.SUM)
            dist.all_reduce(val_count_tensor, op=dist.ReduceOp.SUM)
            val_loss_sum = val_loss_sum_tensor.item()
            val_count = val_count_tensor.item()
        else:
            val_loss_sum = tot_val_loss_sum_rank
            val_count = val_sample_count_rank

        avg_val_loss = val_loss_sum / val_count if val_count > 0 else 0

        # --- End of Epoch Summary & Checkpointing (Master Process Only) ---
        if rank == 0:
            print(f"\n--- Epoch {epoch_idx + 1}/{config['epochs']} Summary ---")
            print(f"Validation Loss: {avg_val_loss:.4f}")
            print(f"Time This Epoch: {format_time(time.time() - epoch_start_time)}")
            print(f"Total Time Elapsed: {format_time(time.time() - start_time)}\n")
            if logger:
                logger.log_metric('val_tokenizer_loss_epoch', avg_val_loss, epoch=epoch_idx)

            if avg_val_loss < best_val_loss:
                best_val_loss = avg_val_loss
                save_path = f"{save_dir}/checkpoints/best_model"
                unwrap_model(model).save_pretrained(save_path)
                print(f"Best model saved to {save_path} (Val Loss: {best_val_loss:.4f})")
                if logger:
                    logger.log_model("best_model", save_path)

        if dist.is_available() and dist.is_initialized():
            dist.barrier()

    dt_result['best_val_loss'] = best_val_loss
    return model, dt_result


def main(config: dict):
    """
    Main function to orchestrate the DDP training process.
    """
    rank, world_size, local_rank = setup_ddp()
    device = torch.device(f"cuda:{local_rank}" if torch.cuda.is_available() else "cpu")
    set_seed(config['seed'], rank)

    save_dir = os.path.join(config['save_path'], config['tokenizer_save_folder_name'])

    # Logger and summary setup (master process only)
    comet_logger, master_summary = None, {}
    if rank == 0:
        os.makedirs(os.path.join(save_dir, 'checkpoints'), exist_ok=True)
        master_summary = {
            'start_time': strftime("%Y-%m-%dT%H-%M-%S", gmtime()),
            'save_directory': save_dir,
            'world_size': world_size,
        }
        if config['use_comet']:
            if comet_ml is None:
                raise RuntimeError("KRONOS_USE_COMET is enabled but comet_ml is not installed.")
            comet_logger = comet_ml.Experiment(
                api_key=config['comet_config']['api_key'],
                project_name=config['comet_config']['project_name'],
                workspace=config['comet_config']['workspace'],
            )
            comet_logger.add_tag(config['comet_tag'])
            comet_logger.set_name(config['comet_name'])
            comet_logger.log_parameters(config)
            print("Comet Logger Initialized.")

    if dist.is_available() and dist.is_initialized():
        dist.barrier()

    # Model Initialization
    model = KronosTokenizer.from_pretrained(config['pretrained_tokenizer_path'])
    model.to(device)
    if dist.is_available() and dist.is_initialized() and world_size > 1:
        ddp_kwargs = {"device_ids": [local_rank]} if torch.cuda.is_available() else {}
        model = DDP(model, find_unused_parameters=False, **ddp_kwargs)

    # torch.compile (opt-in). Kronos 의 rotary attention 등 비표준 연산이 trace 실패할 수 있어
    # fullgraph=False 가 안전. 실패 시 OOM 안전망과 무관하게 즉시 raise 되므로 학습 자체에는 영향 없음.
    if bool(config.get('tokenizer_enable_compile', False)):
        compile_mode = str(config.get('tokenizer_compile_mode', 'reduce-overhead'))
        compile_fullgraph = bool(config.get('tokenizer_compile_fullgraph', False))
        # CUDA torch.compile on this Windows workstation requires Triton during
        # the first compiled forward pass. Without this guard the run can pass
        # torch.compile(...) and then fail before step 1 with
        # "ModuleNotFoundError: No module named 'triton'".
        if torch.cuda.is_available() and importlib.util.find_spec('triton') is None:
            if rank == 0:
                print('[Rank 0] torch.compile skipped - Triton is not installed; using eager mode.')
        else:
            try:
                model = torch.compile(model, mode=compile_mode, fullgraph=compile_fullgraph)
                if rank == 0:
                    print(f"[Rank {rank}] torch.compile enabled - mode={compile_mode} fullgraph={compile_fullgraph}")
            except Exception as compile_exc:
                if rank == 0:
                    print(f"[Rank {rank}] torch.compile failed ({compile_exc}); falling back to eager mode.")

    if rank == 0:
        size_model = model.module if hasattr(model, "module") else model
        print(f"Model Size: {get_model_size(size_model)}")

    # Start Training
    _, dt_result = train_model(
        model, device, config, save_dir, comet_logger, rank, world_size
    )

    # Finalize and save summary (master process only)
    if rank == 0:
        master_summary['final_result'] = dt_result
        with open(os.path.join(save_dir, 'summary.json'), 'w') as f:
            json.dump(master_summary, f, indent=4)
        print('Training finished. Summary file saved.')
        if comet_logger:
            comet_logger.end()

    cleanup_ddp()


if __name__ == '__main__':
    # Usage: torchrun --standalone --nproc_per_node=NUM_GPUS train_tokenizer.py
    disable_ddp = os.getenv("KRONOS_DISABLE_DDP", "").lower() in {"1", "true", "yes", "on"}
    if "WORLD_SIZE" not in os.environ and not disable_ddp:
        raise RuntimeError("This script must be launched with `torchrun`.")

    config_instance = Config()
    main(config_instance.__dict__)
