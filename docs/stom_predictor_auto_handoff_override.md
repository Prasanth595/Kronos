# STOM predictor 자동 고효율 handoff 적용 기록

작성일: 2026-05-14 08:45 KST
대상 run: `stom_1s_grid_pred60_2025_full_small`

## 목적

사용자가 계속 직접 감시하지 않아도, 현재 실행 중인 `--train-stage both` 부모 프로세스가 tokenizer 완료 후 `train_predictor.py`를 실행하는 시점에 predictor 설정을 고효율 값으로 바꿀 수 있게 한다.

## 핵심 문제

현재 살아 있는 부모 프로세스는 이미 다음 설정으로 실행 중이다.

```text
--batch-size 4
--num-workers 0
--train-stage both
```

따라서 이전에 추가한 `--predictor-batch-size`, `--predictor-num-workers` CLI 옵션은 미래의 새 실행에는 유효하지만, 이미 실행 중인 부모 프로세스에는 소급 적용되지 않는다.

## 이번 해결 방식

`train_predictor.py`가 시작될 때 run 디렉터리의 handoff 파일을 읽어 predictor 전용 설정을 덮어쓰게 했다.

기본 파일 위치:

```text
finetune/outputs/stom_1s_grid_pred60_2025_full_small/predictor_handoff_overrides.json
```

현재 배치한 운영 파일 내용의 핵심값:

```json
{
  "enabled": true,
  "batch_size": 16,
  "num_workers": 2
}
```

이 파일은 `finetune/outputs/` 아래에 있어 git ignore 대상이다. 모델 산출물이나 checkpoint를 수정하지 않으며, predictor 프로세스 시작 시점에만 읽힌다.

## 적용 범위

- 현재 tokenizer 단계에는 영향 없음
- tokenizer가 끝난 뒤 새로 시작되는 `train_predictor.py`에만 영향 있음
- `batch_size=4`, `num_workers=0` 대신 `batch_size=16`, `num_workers=2` 적용 예정
- 설정 적용 시 stdout에 다음 형태의 로그가 출력됨

```text
Predictor handoff overrides applied: {'batch_size': 16, 'num_workers': 2} from ...predictor_handoff_overrides.json
```

## 안전 장치

- JSON `enabled=false`이면 적용하지 않음
- 허용 key는 `batch_size`, `num_workers`만 사용
- `batch_size <= 0` 또는 `num_workers < 0`은 오류 처리
- UTF-8 BOM이 있는 Windows PowerShell 생성 JSON도 읽을 수 있게 `utf-8-sig`로 로드
- unknown key는 무시하고 metadata로만 기록

## 남은 감시 포인트

1. tokenizer 100% 도달
2. validation 완료
3. tokenizer checkpoint 생성
4. predictor 시작 로그에서 handoff 적용 메시지 확인
5. predictor의 GPU 사용률, VRAM, samples/sec 확인
6. OOM/RAM/DataLoader 문제가 있으면 `batch_size=8` 또는 `num_workers=0`으로 낮춰 재시도

## 중요 결론

이제 사용자가 계속 직접 감시하지 않아도, 현재 부모 프로세스가 predictor를 실행하는 순간 디스크의 handoff 파일을 통해 고효율 설정이 적용되도록 준비했다. 단, 실제 적용 여부는 predictor 시작 로그와 `/api/training/status`에서 반드시 확인해야 한다.
