import {
  BarChart,
  ChartContainer,
  EvidenceMethodology,
  H1,
  ImprovementDisclosure,
  ImprovementList,
  MetricsGrid,
  ReportSection,
  ReportShell,
  Stack,
  Table,
  Text,
} from "qoder/canvas";

const headlineMetrics = [
  { label: "Overall harness score", value: "6.4/10", tone: "warning" as const },
  { label: "Backend tests", value: "16 pass · 1.4s", tone: "success" as const },
  { label: "Frontend behavioral tests", value: "0", tone: "warning" as const },
  { label: "CI workflows", value: "0", tone: "danger" as const },
];

const dimensionCategories = [
  "Error containment",
  "Backend verification",
  "Bootstrap",
  "Dependency management",
  "Repo hygiene",
  "Frontend verification",
  "Agent conventions",
  "CI automation",
];

const dimensionScores = [9.0, 8.5, 8.0, 7.0, 4.5, 4.0, 4.0, 0.0];

const strengths: string[][] = [
  [
    "Secret-free deterministic test loop",
    "Verification",
    "conftest.py forces AION_DISABLE_MODEL_CALLS=1; 16 tests pass in 1.37s with no keys or network",
  ],
  [
    "Dependency injection makes failure paths testable",
    "Verification",
    "WorkflowRunner accepts an agents dict; FailingPlanner/RejectingCritic fakes assert failure safety, retry limits, exact confidence (0.82)",
  ],
  [
    "Graceful degradation instead of crashes",
    "Error containment",
    "GeminiService returns None when unconfigured; BaseAgent.fallback yields dev-mode output; development_mode is surfaced",
  ],
  [
    "README doubles as a bootstrap contract",
    "Bootstrap",
    "Setup for both apps, env vars, API routes, routing rules, confidence formula, phase status",
  ],
  [
    "Strict static gates on the frontend",
    "Verification",
    "eslint --max-warnings=0 and tsc --noEmit both exit 0 on the current tree",
  ],
  [
    "Clean environment-variable hygiene",
    "Bootstrap",
    "Three .env.example files with safe placeholders; .gitignore negates !.env.example",
  ],
  [
    "Safe error surfaces, tested for leaks",
    "Error containment",
    "Global 500 handler stays generic; a test asserts internal detail never reaches the answer",
  ],
  [
    "Bounded, pinned dependencies",
    "Dependencies",
    "requirements.txt uses >=x,<major; Dockerfiles pin python:3.13-slim and node:22-alpine; multi-stage web build",
  ],
];

const recommendations: string[][] = [
  ["1", "Add minimal GitHub Actions CI (pytest + lint + typecheck + build)", "Highest leverage — the local loop already proves it will pass"],
  ["2", "Write a root AGENTS.md", "Capture interpreter path, per-app directories, and the dev-mode flag"],
  ["3", "Create a one-command check entrypoint (make check)", "Chain every gate in the right directory"],
  ["4", "Introduce Playwright smoke coverage", "Cover the 8 routes and one chat roundtrip before the UI grows"],
  ["5", "Fix compose env wiring + conventional commits", "Real .env with fallback, healthchecks, and navigable history"],
];

export default function AionHarnessReport() {
  return (
    <ReportShell width="wide" ariaLabel="AION harness practices report">
      <Stack gap="section">
        <header>
          <Stack gap="component">
            <H1>AION — Harness Practices Report</H1>
            <Text tone="secondary">
              FastAPI + Next.js monorepo · Phase 3 orchestration · snapshot verified 2026-09-06
            </Text>
            <MetricsGrid variant="header" columns={4} items={headlineMetrics} />
          </Stack>
        </header>

        <ReportSection
          title="Harness dimensions"
          description="Scores across eight harness dimensions; CI automation is the only zero."
          divided
        >
          <ChartContainer
            ariaLabel="Harness dimension scores bar chart"
            footer="Verdict: strong local verification loop, missing enforcement layer."
            caption="Score scale 0–10, derived from live runs and file inspection"
          >
            <BarChart
              categories={dimensionCategories}
              series={[{ name: "Score (0–10)", data: dimensionScores }]}
              horizontal
              domain={[0, 10]}
              valuePrecision={1}
              showLegend={false}
              ariaLabel="Harness dimension scores"
            />
          </ChartContainer>
        </ReportSection>

        <ReportSection
          title="What the harness does well"
          description="Eight verified strengths, anchored to files and a live test run."
          divided
        >
          <Table
            headers={["Strength", "Category", "Verified evidence"]}
            rows={strengths}
            density="compact"
          />
        </ReportSection>

        <ReportSection
          title="Gaps and fixes"
          description="Eight gaps ordered by leverage; each maps to a concrete fix."
          divided
        >
          <ImprovementList summary="1 high · 4 medium · 3 low">
            <ImprovementDisclosure
              severity="high"
              severityTone="danger"
              title="No CI pipeline at all"
              description="Nothing enforces the green state the project already achieves locally; one bad merge can silently break the loop."
              cause="No .github/workflows or other CI config exists anywhere in the repo."
              action="Add a ~30-line GitHub Actions workflow: pytest in apps/api; npm ci + lint + typecheck + build in apps/web, on push/PR."
              defaultOpen
            />
            <ImprovementDisclosure
              severity="medium"
              severityTone="warning"
              title="No agent convention file"
              description="AI assistants rediscover project rules by trial and error, wasting turns and risking wrong commands."
              cause="No AGENTS.md/CLAUDE.md; the apps/api cwd requirement and dev-mode flag are only visible inside conftest.py."
              action="Add a root AGENTS.md: interpreter path (.venv), per-app working directories, AION_DISABLE_MODEL_CALLS flag."
            />
            <ImprovementDisclosure
              severity="medium"
              severityTone="warning"
              title="Frontend has zero behavioral tests"
              description="UI regressions (routing, chat roundtrip, mode switching) ship undetected; the in-progress alert/ feature is unverifiable beyond static checks."
              cause="No Vitest/Jest/Playwright setup; README lists testing as ESLint + TypeScript + Pytest only."
              action="Add Playwright smoke tests for the 8 pages plus one chat roundtrip against the dev-mode API."
            />
            <ImprovementDisclosure
              severity="medium"
              severityTone="warning"
              title="docker-compose wires the example env, not the real env"
              description="Compose always runs in dev-mode with no Gemini key; containers have no readiness gating."
              cause="api service uses env_file: ./apps/api/.env.example; no healthchecks on either service."
              action="Point env_file at apps/api/.env with documented fallback; add healthchecks (curl /health, wget /)."
            />
            <ImprovementDisclosure
              severity="medium"
              severityTone="warning"
              title="Repo hygiene drift"
              description="Low-signal history and uncommitted work make bisecting and agent navigation via git unreliable."
              cause="3 of 5 commits share the message 'Development Commands'; 3 modified files and an untracked apps/web/app/alert/ feature sit in the tree."
              action="Commit or stash WIP; adopt conventional commits (feat/fix/chore)."
            />
            <ImprovementDisclosure
              severity="low"
              severityTone="neutral"
              title="No single verification entrypoint"
              description="Multi-step verification across two directories invites skipped steps, especially for automated agents."
              cause="Commands live in two README sections; no Makefile/justfile/root script chains them."
              action="Add a root make check chaining backend pytest + frontend lint/typecheck/build."
            />
            <ImprovementDisclosure
              severity="low"
              severityTone="neutral"
              title="Runtime version drift between local and container"
              description="Code verified locally on Python 3.14 may behave differently in the 3.13 container; a TestClient deprecation warning signals a coming break."
              cause="Local .venv is Python 3.14 while the API Dockerfile pins python:3.13-slim; Starlette TestClient warns about the httpx/httpx2 transition."
              action="Align .venv and Dockerfile on one Python minor version; plan the httpx2 migration."
            />
            <ImprovementDisclosure
              severity="low"
              severityTone="neutral"
              title="Test dependencies mixed into runtime requirements"
              description="Production containers carry test tooling; dependency intent is blurred."
              cause="requirements.txt ships pytest alongside fastapi/uvicorn/pydantic."
              action="Split into requirements.txt + requirements-dev.txt."
            />
          </ImprovementList>
        </ReportSection>

        <ReportSection
          title="Top recommendations"
          description="Five moves, ordered by leverage."
          divided
        >
          <Table
            headers={["Priority", "Action", "Why"]}
            rows={recommendations}
            density="compact"
            rowTone={["accent", undefined, undefined, undefined, undefined]}
          />
        </ReportSection>

        <ReportSection
          title="Methodology"
          description="Every claim traces to a live run or a read file."
          divided
        >
          <EvidenceMethodology
            title="How this report was verified"
            summary="One live verification run plus static inspection of harness-relevant files."
            groups={[
              {
                title: "Live verification run",
                items: [
                  { label: "Backend tests", value: "16 passed in 1.37s (pytest, no credentials)" },
                  { label: "Frontend lint", value: "pass — eslint . --max-warnings=0" },
                  { label: "Frontend typecheck", value: "pass — tsc --noEmit" },
                  { label: "Docker build", value: "not exercised in this run" },
                ],
              },
              {
                title: "Static inspection",
                items: [
                  {
                    label: "Core files read",
                    value:
                      "README, docker-compose, 2 Dockerfiles, requirements, package.json, conftest, 2 test files, config, main, workflow_runner, gemini service, base agent",
                  },
                  { label: "Git history", value: "5 commits; 3 share one message" },
                  {
                    label: "Harness convention files",
                    value: "none found (AGENTS.md/CLAUDE.md/.cursorrules/CI)",
                  },
                ],
              },
            ]}
          />
        </ReportSection>

        <Text tone="secondary" size="small">
          Generated 2026-09-06 · Source: findings.json (better-harness snapshot 223631-aion)
        </Text>
      </Stack>
    </ReportShell>
  );
}
