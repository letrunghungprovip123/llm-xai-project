import { spawn } from "node:child_process";

type StageCommand = {
  executable: "python3" | "tsx";
  arguments: string[];
};

const STAGE_COMMANDS: Record<string, StageCommand> = {
  "ml:data-audit": {
    executable: "python3",
    arguments: ["-m", "research.ml.data_audit.main"],
  },
  "ml:target-audit": {
    executable: "python3",
    arguments: ["-m", "research.ml.target_audit.main"],
  },
  "ml:features": {
    executable: "python3",
    arguments: ["-m", "research.ml.feature_engineering.main"],
  },
  "ml:matrix": {
    executable: "python3",
    arguments: ["-m", "research.ml.feature_matrix.main"],
  },
  "ml:split": {
    executable: "python3",
    arguments: ["-m", "research.ml.data_split.main"],
  },
  "ml:preprocess": {
    executable: "python3",
    arguments: ["-m", "research.ml.preprocessing.main"],
  },
  "ml:train": {
    executable: "python3",
    arguments: ["-m", "research.ml.modeling.main"],
  },
  "ml:xai": {
    executable: "python3",
    arguments: ["-m", "research.ml.xai.main"],
  },
  "ml:xai-quality": {
    executable: "python3",
    arguments: ["-m", "research.ml.xai.quality.main"],
  },
  "ml:ir": {
    executable: "python3",
    arguments: ["-m", "research.ml.explanation_ir.main"],
  },
  "ml:evidence": {
    executable: "python3",
    arguments: ["-m", "research.ml.evidence_exposure.main"],
  },
  "llm:generate": {
    executable: "tsx",
    arguments: ["research/llm/narrative/main.ts"],
  },
  "llm:aggregate": {
    executable: "tsx",
    arguments: ["research/llm/narrative/aggregate-main.ts"],
  },
  "llm:filter-deepseek": {
    executable: "tsx",
    arguments: ["research/llm/canonicalization/filter-main.ts"],
  },
  "llm:canonicalize": {
    executable: "tsx",
    arguments: ["research/llm/canonicalization/main.ts"],
  },
  "llm:contract": {
    executable: "tsx",
    arguments: ["research/llm/contract_validation/main.ts"],
  },
  "llm:claims": {
    executable: "tsx",
    arguments: ["research/llm/claim_extraction/main.ts"],
  },
};

function printUsage(): void {
  const stages = Object.keys(STAGE_COMMANDS).sort();
  console.log("Cách dùng: npm run research -- <stage> [arguments]");
  console.log("");
  console.log("Các stage hiện có:");
  for (const stage of stages) {
    console.log(`  ${stage}`);
  }
}

function runStage(stageName: string, forwardedArguments: string[]): void {
  const command = STAGE_COMMANDS[stageName];
  if (!command) {
    console.error(`Stage không hợp lệ: ${stageName}`);
    printUsage();
    process.exitCode = 2;
    return;
  }

  const child = spawn(
    command.executable,
    [...command.arguments, ...forwardedArguments],
    { stdio: "inherit" },
  );

  child.on("error", (error) => {
    console.error(`Không thể chạy ${stageName}: ${error.message}`);
    process.exitCode = 1;
  });

  child.on("exit", (code, signal) => {
    if (signal) {
      console.error(`Stage ${stageName} dừng bởi signal ${signal}.`);
      process.exitCode = 1;
      return;
    }
    process.exitCode = code ?? 1;
  });
}

const [stageName, ...forwardedArguments] = process.argv.slice(2);

if (!stageName || stageName === "--help" || stageName === "-h") {
  printUsage();
} else {
  runStage(stageName, forwardedArguments);
}
