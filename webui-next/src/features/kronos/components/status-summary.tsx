import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import type { DataInfo, ServerStatus } from "../types";

function ServerStatusDot({ status }: { status: ServerStatus }) {
  const dotClass =
    status === "loading-model"
      ? "bg-orange-500"
      : status === "running"
        ? "bg-green-500"
        : status === "offline"
          ? "bg-red-500"
          : "bg-muted-foreground";
  const label =
    status === "loading-model"
      ? "Đang tải model"
      : status === "running"
        ? "Đang chạy"
        : status === "offline"
          ? "Không chạy"
          : "Đang kiểm tra";

  return (
    <div className="mt-1 flex min-w-0 items-center gap-2 font-semibold">
      <span
        aria-hidden="true"
        className={cn(
          "size-2.5 shrink-0 rounded-full ring-4 ring-muted",
          dotClass,
        )}
      />
      <span className="truncate">{label}</span>
    </div>
  );
}

export function StatusSummary({
  dataInfo,
  modelLoaded,
  selectedDevice,
  serverStatus,
}: {
  dataInfo: DataInfo | null;
  modelLoaded: boolean;
  selectedDevice: string;
  serverStatus: ServerStatus;
}) {
  return (
    <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
      <Card className="rounded-md py-2">
        <CardContent className="px-3">
          <div className="text-xs font-medium text-muted-foreground">Server</div>
          <ServerStatusDot status={serverStatus} />
        </CardContent>
      </Card>
      <Card className="rounded-md py-2">
        <CardContent className="px-3">
          <div className="text-xs font-medium text-muted-foreground">Model</div>
          <div className="mt-1 font-semibold">{modelLoaded ? "Đã tải" : "Chưa tải"}</div>
        </CardContent>
      </Card>
      <Card className="rounded-md py-2">
        <CardContent className="px-3">
          <div className="text-xs font-medium text-muted-foreground">Dữ liệu</div>
          <div className="mt-1 font-semibold">{dataInfo ? `${dataInfo.rows} dòng` : "--"}</div>
        </CardContent>
      </Card>
      <Card className="rounded-md py-2">
        <CardContent className="px-3">
          <div className="text-xs font-medium text-muted-foreground">Thiết bị</div>
          <div className="mt-1 font-semibold uppercase">{selectedDevice}</div>
        </CardContent>
      </Card>
    </div>
  );
}
