import { Cpu, Loader2, Power, RefreshCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { LoadingAction, ModelInfo } from "../types";
import { FieldLabel } from "./field-label";
import { PanelTitle } from "./panel-title";

export function ModelPanel({
  loadingAction,
  modelLoaded,
  models,
  onLoadModel,
  onSelectedDeviceChange,
  onSelectedModelChange,
  onUnloadModel,
  selectedDevice,
  selectedModel,
}: {
  loadingAction: LoadingAction;
  modelLoaded: boolean;
  models: Record<string, ModelInfo>;
  onLoadModel: () => void;
  onSelectedDeviceChange: (value: string) => void;
  onSelectedModelChange: (value: string) => void;
  onUnloadModel: () => void;
  selectedDevice: string;
  selectedModel: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <PanelTitle icon={<Cpu className="size-4" />} title="Mô hình" />
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col gap-4">
        <div>
          <FieldLabel>Chọn mô hình</FieldLabel>
          <Select
            onValueChange={onSelectedModelChange}
            value={selectedModel}
          >
            <SelectTrigger className="h-11 w-full">
              <SelectValue placeholder="Chọn mô hình" />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                {Object.entries(models).map(([key, model]) => (
                  <SelectItem key={key} value={key}>
                    {model.name} ({model.params}) - {model.description}
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
        </div>

        <div>
          <FieldLabel>Thiết bị chạy</FieldLabel>
          <Select
            onValueChange={onSelectedDeviceChange}
            value={selectedDevice}
          >
            <SelectTrigger className="h-11 w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectItem value="cpu">CPU</SelectItem>
                <SelectItem value="cuda">CUDA</SelectItem>
                <SelectItem value="mps">MPS</SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
        </div>

        <Button
          className="h-11 w-full"
          disabled={loadingAction === "model" || loadingAction === "unload" || !selectedModel}
          onClick={onLoadModel}
          type="button"
        >
          {loadingAction === "model" ? (
            <Loader2 data-icon="inline-start" className="animate-spin" />
          ) : (
            <RefreshCcw data-icon="inline-start" />
          )}
          Tải mô hình
        </Button>

        <Button
          variant="destructive"
          className="h-11 w-full"
          disabled={!modelLoaded || loadingAction === "model" || loadingAction === "unload"}
          onClick={onUnloadModel}
          type="button"
        >
          {loadingAction === "unload" ? (
            <Loader2 data-icon="inline-start" className="animate-spin" />
          ) : (
            <Power data-icon="inline-start" />
          )}
          Gỡ model
        </Button>
        </div>
      </CardContent>
    </Card>
  );
}
