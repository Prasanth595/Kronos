import { Database, Loader2 } from "lucide-react";
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
import { formatDate, formatNumber } from "../lib/format";
import type { DataFile, DataInfo, LoadingAction } from "../types";
import { FieldLabel } from "./field-label";
import { PanelTitle } from "./panel-title";

export function DataPanel({
  dataFiles,
  dataInfo,
  loadingAction,
  onLoadData,
  onSelectedFileChange,
  selectedFile,
}: {
  dataFiles: DataFile[];
  dataInfo: DataInfo | null;
  loadingAction: LoadingAction;
  onLoadData: () => void;
  onSelectedFileChange: (value: string) => void;
  selectedFile: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <PanelTitle icon={<Database className="size-4" />} title="Dữ liệu" />
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col gap-4">
        <div>
          <FieldLabel>Chọn file dữ liệu</FieldLabel>
          <Select
            onValueChange={(value) => onSelectedFileChange(value === "__none__" ? "" : value)}
            value={selectedFile || "__none__"}
          >
            <SelectTrigger className="h-11 w-full">
              <SelectValue placeholder="Chọn file" />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectItem value="__none__">Chọn file</SelectItem>
                {dataFiles.map((file) => (
                  <SelectItem key={file.path} value={file.path}>
                    {file.name} ({file.size})
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
        </div>

        <Button
          variant="outline"
          className="h-11 w-full"
          disabled={loadingAction === "data" || !selectedFile}
          onClick={onLoadData}
          type="button"
        >
          {loadingAction === "data" ? (
            <Loader2 data-icon="inline-start" className="animate-spin" />
          ) : (
            <Database data-icon="inline-start" />
          )}
          Tải dữ liệu
        </Button>

        {dataInfo && (
          <dl className="grid grid-cols-2 gap-3 rounded-md border bg-muted/40 p-3 text-sm">
            <div>
              <dt className="text-xs font-semibold text-muted-foreground">Số dòng</dt>
              <dd className="mt-1 font-semibold">{dataInfo.rows}</dd>
            </div>
            <div>
              <dt className="text-xs font-semibold text-muted-foreground">Khung</dt>
              <dd className="mt-1 font-semibold">{dataInfo.timeframe}</dd>
            </div>
            <div className="col-span-2">
              <dt className="text-xs font-semibold text-muted-foreground">Thời gian</dt>
              <dd className="mt-1 font-medium">
                {formatDate(dataInfo.start_date)} - {formatDate(dataInfo.end_date)}
              </dd>
            </div>
            <div className="col-span-2">
              <dt className="text-xs font-semibold text-muted-foreground">Khoảng giá</dt>
              <dd className="mt-1 font-medium">
                {formatNumber(dataInfo.price_range.min)} - {formatNumber(dataInfo.price_range.max)}
              </dd>
            </div>
          </dl>
        )}
        </div>
      </CardContent>
    </Card>
  );
}
