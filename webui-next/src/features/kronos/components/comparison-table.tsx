import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDate, formatNumber } from "../lib/format";
import type { PredictionResponse } from "../types";

export function ComparisonTable({ result }: { result: PredictionResponse | null }) {
  return (
    <div className="max-h-[420px] overflow-auto border-t">
      <Table className="min-w-[920px] border-collapse">
        <TableHeader className="sticky top-0 bg-background text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          <TableRow>
            <TableHead className="px-4 py-3 text-left">Thời gian</TableHead>
            <TableHead className="px-4 py-3 text-right">Open TT</TableHead>
            <TableHead className="px-4 py-3 text-right">Open DB</TableHead>
            <TableHead className="px-4 py-3 text-right">High TT</TableHead>
            <TableHead className="px-4 py-3 text-right">High DB</TableHead>
            <TableHead className="px-4 py-3 text-right">Low TT</TableHead>
            <TableHead className="px-4 py-3 text-right">Low DB</TableHead>
            <TableHead className="px-4 py-3 text-right">Close TT</TableHead>
            <TableHead className="px-4 py-3 text-right">Close DB</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {result?.prediction_results.length ? (
            result.prediction_results.slice(0, 120).map((prediction, index) => {
              const actual = result.actual_data[index];
              return (
                <TableRow key={`${prediction.timestamp}-${index}`}>
                  <TableCell className="px-4 py-3 font-mono text-xs">
                    {formatDate(prediction.timestamp)}
                  </TableCell>
                  <TableCell className="px-4 py-3 text-right">
                    {formatNumber(actual?.open)}
                  </TableCell>
                  <TableCell className="px-4 py-3 text-right">
                    {formatNumber(prediction.open)}
                  </TableCell>
                  <TableCell className="px-4 py-3 text-right">
                    {formatNumber(actual?.high)}
                  </TableCell>
                  <TableCell className="px-4 py-3 text-right">
                    {formatNumber(prediction.high)}
                  </TableCell>
                  <TableCell className="px-4 py-3 text-right">
                    {formatNumber(actual?.low)}
                  </TableCell>
                  <TableCell className="px-4 py-3 text-right">
                    {formatNumber(prediction.low)}
                  </TableCell>
                  <TableCell className="px-4 py-3 text-right">
                    {formatNumber(actual?.close)}
                  </TableCell>
                  <TableCell className="px-4 py-3 text-right">
                    {formatNumber(prediction.close)}
                  </TableCell>
                </TableRow>
              );
            })
          ) : (
            <TableRow>
              <TableCell className="px-4 py-12 text-center text-muted-foreground" colSpan={9}>
                Bảng so sánh sẽ xuất hiện sau khi chạy dự báo.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );
}
