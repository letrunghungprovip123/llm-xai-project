import { spawn } from "node:child_process";

type StageCommand = {
  executable: "python3" | "tsx";
  entrypoint: string;
};

const STAGE_COMMANDS: Record<string, StageCommand> = {
  "ml:data-audit": {
    executable: "python3",
    entrypoint: "ml/scripts/run_00_02_first_batch.py",
  },
  "ml:target-audit": {
    executable: "python3",
    entrypoint: "ml/scripts/run_a2_target_missing_audit.py",
  },
  "ml:features": {
    executable: "python3",
    entrypoint: "ml/scripts/run_b_feature_engineering_layer.py",
  },
  "ml:matrix": {
    executable: "python3",
    entrypoint: "ml/scripts/run_c_feature_matrix_registry_layer.py",
  },
  "ml:split": {
    executable: "python3",
    entrypoint: "ml/scripts/run_d_leakage_split_layer.py",
  },
  "ml:preprocess": {
    executable: "python3",
    entrypoint: "ml/scripts/run_e_preprocessing_layer.py",
  },
  "ml:train": {
    executable: "python3",
    entrypoint: "ml/scripts/model_layer/run_f_model_training_layer.py",
  },
  "ml:xai": {
    executable: "python3",
    entrypoint: "ml/scripts/xai_layer/run_g_xai_evidence_layer.py",
  },
  "ml:ir": {
    executable: "python3",
    entrypoint: "ml/scripts/explanation_ir_layer/run_h_explanation_ir_layer.py",
  },
  "ml:evidence": {
    executable: "python3",
    entrypoint: "ml/scripts/evidence_exposure_layer/main.py",
  },
  "llm:generate": {
    executable: "tsx",
    entrypoint: "batch/llm-narrative/run.ts",
  },
  "llm:aggregate": {
    executable: "tsx",
    entrypoint: "batch/llm-narrative/aggregate.ts",
  },
  "llm:filter-deepseek": {
    executable: "tsx",
    entrypoint: "batch/llm-validation/filter-deepseek-eval36.ts",
  },
  "llm:canonicalize": {
    executable: "tsx",
    entrypoint: "batch/llm-validation/build-generation-index.ts",
  },
  "llm:contract": {
    executable: "tsx",
    entrypoint: "batch/llm-validation/run-contract-validation.ts",
  },
  "llm:claims": {
    executable: "tsx",
    entrypoint: "batch/llm-validation/run-claim-extraction.ts",
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
    [command.entrypoint, ...forwardedArguments],
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
