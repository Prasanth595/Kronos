"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { AlertCircle, BarChart3, CheckCircle2 } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import {
  fetchAvailableModels,
  fetchDataFiles,
  fetchServerHealth,
  loadDataFile,
  loadModel,
  runPrediction,
  unloadModel,
} from "../api/client";
import { LOOKBACK, PRED_LEN, WINDOW_SIZE } from "../lib/constants";
import { getMetrics } from "../lib/metrics";
import { getWindowDates } from "../lib/windowing";
import type {
  DataFile,
  DataInfo,
  LoadingAction,
  ModelInfo,
  PredictionResponse,
  ServerStatus,
  StatusMessage,
} from "../types";
import { ComparisonTable } from "./comparison-table";
import { DataPanel } from "./data-panel";
import { MetricsSummary } from "./metrics-summary";
import { ModelPanel } from "./model-panel";
import { PredictionPanel } from "./prediction-panel";
import { PriceChart } from "./price-chart";
import { StatusSummary } from "./status-summary";

function Status({ status }: { status: StatusMessage | null }) {
  if (!status) return null;

  const Icon = status.type === "success" ? CheckCircle2 : AlertCircle;

  return (
    <Alert
      className="rounded-md px-3 py-2"
      variant={status.type === "error" ? "destructive" : "default"}
    >
      <Icon className="mt-0.5 size-4 shrink-0" />
      <AlertDescription className="text-current">{status.text}</AlertDescription>
    </Alert>
  );
}

export function KronosDashboard() {
  const [models, setModels] = useState<Record<string, ModelInfo>>({});
  const [dataFiles, setDataFiles] = useState<DataFile[]>([]);
  const [selectedModel, setSelectedModel] = useState("kronos-mini");
  const [selectedDevice, setSelectedDevice] = useState("cpu");
  const [selectedFile, setSelectedFile] = useState("");
  const [modelLoaded, setModelLoaded] = useState(false);
  const [dataInfo, setDataInfo] = useState<DataInfo | null>(null);
  const [status, setStatus] = useState<StatusMessage | null>(null);
  const [snackbar, setSnackbar] = useState<StatusMessage | null>(null);
  const [serverStatus, setServerStatus] = useState<ServerStatus>("checking");
  const [loadingAction, setLoadingAction] = useState<LoadingAction>(null);
  const [startPercent, setStartPercent] = useState(0.1);
  const [temperature, setTemperature] = useState(1);
  const [topP, setTopP] = useState(0.9);
  const [sampleCount, setSampleCount] = useState(1);
  const [result, setResult] = useState<PredictionResponse | null>(null);

  const metrics = useMemo(() => getMetrics(result), [result]);
  const windowDates = useMemo(() => getWindowDates(dataInfo, startPercent), [dataInfo, startPercent]);
  const windowPercent = dataInfo ? Math.min((WINDOW_SIZE / dataInfo.rows) * 100, 100) : 0;
  const canPredict = modelLoaded && Boolean(dataInfo) && Boolean(selectedFile);

  const refreshServerStatus = useCallback(async () => {
    try {
      const health = await fetchServerHealth();
      setServerStatus("running");
      setModelLoaded(health.model_loaded);
    } catch {
      setServerStatus("offline");
      setModelLoaded(false);
    }
  }, []);

  useEffect(() => {
    async function bootstrap() {
      setLoadingAction("models");
      try {
        const [healthResponse, modelsResponse, filesResponse] = await Promise.all([
          fetchServerHealth(),
          fetchAvailableModels(),
          fetchDataFiles(),
        ]);
        setServerStatus("running");
        setModelLoaded(healthResponse.model_loaded);
        setModels(modelsResponse.models);
        setDataFiles(filesResponse);
        const firstFile = filesResponse[0]?.path ?? "";
        setSelectedFile(firstFile);
        setStatus({
          type: "info",
          text: "Đã sẵn sàng. Hãy tải mô hình và dữ liệu để bắt đầu dự báo.",
        });
      } catch (error) {
        setServerStatus("offline");
        setStatus({
          type: "error",
          text: error instanceof Error ? error.message : "Không khởi tạo được giao diện",
        });
      } finally {
        setLoadingAction(null);
      }
    }

    bootstrap();
  }, []);

  useEffect(() => {
    if (loadingAction === "model") return;

    const interval = window.setInterval(refreshServerStatus, 10000);
    return () => window.clearInterval(interval);
  }, [loadingAction, refreshServerStatus]);

  useEffect(() => {
    if (loadingAction !== "model") return;

    let cancelled = false;

    async function checkLoadedModel() {
      try {
        const health = await fetchServerHealth();
        if (cancelled || !health.model_loaded) return;

        setModelLoaded(true);
        setServerStatus("running");
        setLoadingAction(null);
        setSnackbar({
          type: "success",
          text: "Mô hình đã tải xong và sẵn sàng trên server.",
        });
      } catch {
        if (!cancelled) {
          setServerStatus("offline");
        }
      }
    }

    void checkLoadedModel();
    const interval = window.setInterval(checkLoadedModel, 2000);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [loadingAction]);

  useEffect(() => {
    if (!snackbar) return;

    if (snackbar.type === "success") toast.success(snackbar.text, { duration: 4500 });
    if (snackbar.type === "info") toast.info(snackbar.text, { duration: 4500 });
    if (snackbar.type === "warning") toast.warning(snackbar.text, { duration: 4500 });
    if (snackbar.type === "error") toast.error(snackbar.text, { duration: 4500 });

    const timeout = window.setTimeout(() => {
      setSnackbar(null);
    }, 4500);

    return () => window.clearTimeout(timeout);
  }, [snackbar]);

  async function handleLoadModel() {
    setLoadingAction("model");
    setServerStatus("loading-model");
    setStatus(null);
    setSnackbar(null);
    try {
      const response = await loadModel(selectedModel, selectedDevice);
      setModelLoaded(true);
      setServerStatus("running");
      setSnackbar({ type: "success", text: response.message });
    } catch (error) {
      setModelLoaded(false);
      setSnackbar(null);
      setServerStatus("running");
      setStatus({
        type: "error",
        text: error instanceof Error ? error.message : "Tải mô hình thất bại",
      });
      void refreshServerStatus();
    } finally {
      setLoadingAction(null);
    }
  }

  async function handleUnloadModel() {
    setLoadingAction("unload");
    setStatus(null);
    setSnackbar(null);
    try {
      const response = await unloadModel();
      setModelLoaded(false);
      setResult(null);
      setServerStatus("running");
      setSnackbar({ type: "success", text: response.message });
    } catch (error) {
      setStatus({
        type: "error",
        text: error instanceof Error ? error.message : "Gỡ mô hình thất bại",
      });
      void refreshServerStatus();
    } finally {
      setLoadingAction(null);
    }
  }

  async function handleLoadData() {
    if (!selectedFile) {
      setStatus({ type: "warning", text: "Vui lòng chọn file dữ liệu trước." });
      return;
    }

    setLoadingAction("data");
    setStatus(null);
    try {
      const response = await loadDataFile(selectedFile);
      setDataInfo(response.data_info);
      setResult(null);
      setStartPercent(0.1);
      setStatus({ type: "success", text: response.message });
    } catch (error) {
      setStatus({
        type: "error",
        text: error instanceof Error ? error.message : "Tải dữ liệu thất bại",
      });
    } finally {
      setLoadingAction(null);
    }
  }

  async function handlePredict() {
    if (!dataInfo || !selectedFile) return;

    setLoadingAction("predict");
    setStatus(null);
    try {
      const response = await runPrediction({
        file_path: selectedFile,
        lookback: LOOKBACK,
        pred_len: PRED_LEN,
        start_date: (windowDates.startDate ?? new Date(dataInfo.start_date))
          .toISOString()
          .slice(0, 16),
        temperature,
        top_p: topP,
        sample_count: sampleCount,
      });
      setResult(response);
      setStatus({ type: "success", text: response.message });
    } catch (error) {
      setStatus({
        type: "error",
        text: error instanceof Error ? error.message : "Dự báo thất bại",
      });
    } finally {
      setLoadingAction(null);
    }
  }

  return (
    <main className="min-h-screen bg-background px-5 py-6 text-foreground lg:px-8">
      <div className="mx-auto flex max-w-[1600px] flex-col gap-5">
        <header className="flex flex-col gap-4 border-b pb-5 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-foreground lg:text-3xl">
              Kronos - Dự báo tài chính
            </h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
              Workflow dự báo K-line: tải mô hình, chọn dữ liệu,
              sinh dự báo và so sánh với dữ liệu thực tế trên một màn hình.
            </p>
          </div>
          <StatusSummary
            dataInfo={dataInfo}
            modelLoaded={modelLoaded}
            selectedDevice={selectedDevice}
            serverStatus={serverStatus}
          />
        </header>

        <div className="grid gap-5 xl:grid-cols-[400px_minmax(0,1fr)]">
          <aside className="flex flex-col gap-4">
            <ModelPanel
              loadingAction={loadingAction}
              modelLoaded={modelLoaded}
              models={models}
              onLoadModel={handleLoadModel}
              onSelectedDeviceChange={setSelectedDevice}
              onSelectedModelChange={setSelectedModel}
              onUnloadModel={handleUnloadModel}
              selectedDevice={selectedDevice}
              selectedModel={selectedModel}
            />

            <DataPanel
              dataFiles={dataFiles}
              dataInfo={dataInfo}
              loadingAction={loadingAction}
              onLoadData={handleLoadData}
              onSelectedFileChange={setSelectedFile}
              selectedFile={selectedFile}
            />

            <PredictionPanel
              canPredict={canPredict}
              dataInfo={dataInfo}
              loadingAction={loadingAction}
              onPredict={handlePredict}
              onSampleCountChange={setSampleCount}
              onStartPercentChange={setStartPercent}
              onTemperatureChange={setTemperature}
              onTopPChange={setTopP}
              sampleCount={sampleCount}
              startPercent={startPercent}
              temperature={temperature}
              topP={topP}
              windowDates={windowDates}
              windowPercent={windowPercent}
            />

            <Status status={status} />
          </aside>

          <div className="flex min-w-0 flex-col gap-4">
            <PriceChart result={result} />

            <Card>
              <CardHeader className="flex flex-col gap-2 px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-foreground">So sánh dự báo</h2>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {result?.prediction_type ?? "Chạy dự báo để xem sai số và bảng chi tiết."}
                  </p>
                </div>
                <BarChart3 className="size-5 text-muted-foreground" />
              </CardHeader>
              <Separator />
              <CardContent className="p-0">
                <MetricsSummary metrics={metrics} />
                <ComparisonTable result={result} />
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </main>
  );
}
