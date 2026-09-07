import { AlertCircle, KeyRound, RotateCcw, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";

export function ChatErrorState({
  onRetry,
  onQuick,
  errorDetail,
}: {
  onRetry: () => void;
  onQuick: () => void;
  errorDetail?: string | null;
}) {
  // Detect common error types from the detail message
  const isApiKeyIssue =
    errorDetail &&
    (errorDetail.includes("GEMINI_API_KEY") ||
      errorDetail.includes("API key") ||
      errorDetail.includes("401") ||
      errorDetail.includes("403"));

  return (
    <div
      role="alert"
      className="ml-12 max-w-xl rounded-[20px] border border-[#efcaca] bg-[#fff5f5] p-4">
      <div className="flex gap-3">
        {isApiKeyIssue ? (
          <KeyRound className="mt-0.5 size-5 shrink-0 text-[#b53d3d]" />
        ) : (
          <AlertCircle className="mt-0.5 size-5 shrink-0 text-[#b53d3d]" />
        )}
        <div>
          <p className="text-sm font-semibold">
            {isApiKeyIssue
              ? "AI model configuration issue"
              : "AION could not complete this task"}
          </p>
          <p className="mt-1 text-xs leading-5 text-muted-text">
            {errorDetail ??
              "The workflow stopped safely. No internal error details or credentials were exposed."}
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button size="sm" onClick={onRetry}>
              <RotateCcw className="mr-1.5 size-3.5" />
              Retry
            </Button>
            <Button size="sm" variant="outline" onClick={onQuick}>
              <Zap className="mr-1.5 size-3.5" />
              Switch to Quick Answer
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
