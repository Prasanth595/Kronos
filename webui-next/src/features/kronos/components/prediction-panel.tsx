import { Info, Loader2, Play, SlidersHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { LOOKBACK, PRED_LEN, WINDOW_SIZE } from "../lib/constants";
import { formatDate } from "../lib/format";
import type { DataInfo, LoadingAction } from "../types";
import { PanelTitle } from "./panel-title";

function InfoLabel({
  children,
  tooltip,
}: {
  children: React.ReactNode;
  tooltip: string;
}) {
  return (
    <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-foreground">
      <span>{children}</span>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon-xs"
          aria-label={`Giải thích: ${tooltip}`}
          className="size-5 rounded-full"
          type="button"
          >
            <Info />
          </Button>
        </TooltipTrigger>
        <TooltipContent className="max-w-72">
          {tooltip}
        </TooltipContent>
      </Tooltip>
    </div>
  );
}

export function PredictionPanel({
  canPredict,
  dataInfo,
  loadingAction,
  onPredict,
  onSampleCountChange,
  onStartPercentChange,
  onTemperatureChange,
  onTopPChange,
  sampleCount,
  startPercent,
  temperature,
  topP,
  windowDates,
  windowPercent,
}: {
  canPredict: boolean;
  dataInfo: DataInfo | null;
  loadingAction: LoadingAction;
  onPredict: () => void;
  onSampleCountChange: (value: number) => void;
  onStartPercentChange: (value: number) => void;
  onTemperatureChange: (value: number) => void;
  onTopPChange: (value: number) => void;
  sampleCount: number;
  startPercent: number;
  temperature: number;
  topP: number;
  windowDates: { startDate: Date | null; endDate: Date | null };
  windowPercent: number;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <PanelTitle icon={<SlidersHorizontal className="size-4" />} title="Dự báo" />
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col gap-5">
        <div>
          <div className="mb-2 flex items-center justify-between text-sm">
            <span className="font-semibold text-foreground">Cửa sổ dữ liệu</span>
            <span className="text-muted-foreground">{WINDOW_SIZE} điểm</span>
          </div>
          <div className="rounded-md border bg-muted/40 p-3">
            <div className="mb-2 grid grid-cols-2 gap-2 text-xs text-muted-foreground">
              <span>Bắt đầu: {formatDate(windowDates.startDate?.toISOString())}</span>
              <span>Kết thúc: {formatDate(windowDates.endDate?.toISOString())}</span>
            </div>
            <Slider
              disabled={!dataInfo}
              max={Math.max(100 - windowPercent, 0)}
              min={0}
              onValueChange={([value]) => onStartPercentChange(value / 100)}
              step={0.1}
              value={[Math.min(startPercent * 100, Math.max(100 - windowPercent, 0))]}
            />
            <div className="mt-2 flex justify-between text-xs text-muted-foreground">
              <span>400 lịch sử</span>
              <span>120 dự báo</span>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-md border bg-muted/40 p-3">
            <div className="text-xs font-semibold text-muted-foreground">Lookback</div>
            <div className="mt-1 text-lg font-semibold">{LOOKBACK}</div>
          </div>
          <div className="rounded-md border bg-muted/40 p-3">
            <div className="text-xs font-semibold text-muted-foreground">Pred len</div>
            <div className="mt-1 text-lg font-semibold">{PRED_LEN}</div>
          </div>
        </div>

        <div>
          <InfoLabel tooltip="Điều chỉnh mức ngẫu nhiên khi model sinh dự báo. Giá trị thấp cho kết quả ổn định hơn; giá trị cao cho dự báo đa dạng hơn nhưng dễ dao động hơn.">
            Nhiệt độ dự báo: {temperature.toFixed(1)}
          </InfoLabel>
          <Slider
            max={2}
            min={0.1}
            onValueChange={([value]) => onTemperatureChange(value)}
            step={0.1}
            value={[temperature]}
          />
        </div>

        <div>
          <InfoLabel tooltip="Giới hạn nhóm khả năng mà model được phép chọn khi dự báo. Top-p thấp làm kết quả thận trọng hơn; Top-p cao cho phép nhiều kịch bản hơn.">
            Top-p: {topP.toFixed(1)}
          </InfoLabel>
          <Slider
            max={1}
            min={0.1}
            onValueChange={([value]) => onTopPChange(value)}
            step={0.1}
            value={[topP]}
          />
        </div>

        <div>
          <InfoLabel tooltip="Số lần model sinh mẫu dự báo cho cùng một cửa sổ dữ liệu. Số mẫu lớn hơn có thể ổn định kết quả hơn, nhưng sẽ chạy chậm hơn.">
            Số mẫu dự báo
          </InfoLabel>
          <Input
            className="h-11"
            max={5}
            min={1}
            onChange={(event) => onSampleCountChange(Number(event.target.value))}
            type="number"
            value={sampleCount}
          />
        </div>

        <Button
          className="h-12 w-full"
          disabled={!canPredict || loadingAction === "predict"}
          onClick={onPredict}
          type="button"
        >
          {loadingAction === "predict" ? (
            <Loader2 data-icon="inline-start" className="animate-spin" />
          ) : (
            <Play data-icon="inline-start" />
          )}
          Bắt đầu dự báo
        </Button>
        </div>
      </CardContent>
    </Card>
  );
}
