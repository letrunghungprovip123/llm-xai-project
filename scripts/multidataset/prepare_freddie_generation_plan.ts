import path from "node:path";
import { buildFreddieGenerationPlan } from "../../research/ts/replication/generationPlan";

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  const result = await buildFreddieGenerationPlan({
    workspace: required(args, "workspace"),
    evidencePath: optional(args, "evidence"),
    m16ReceiptPath: optional(args, "m16-receipt"),
    outputDir: optional(args, "output-dir"),
    experimentId: optional(args, "experiment-id"),
  });
  console.log(`PASS cases=${result.caseCount} planned_generations=${result.jobCount}`);
  console.log(`REPLICATION_PROTOCOL_SHA256=${result.protocolSha256}`);
  console.log(`FREDDIE_M17A_PLAN_DIR=${path.resolve(result.planDir)}`);
  console.log("FREDDIE_SFLLD_M17A_PLAN=PASS");
}

function parseArgs(values: string[]): Map<string,string> { const m=new Map<string,string>(); for(let i=0;i<values.length;i+=2){const k=values[i],v=values[i+1]; if(!k?.startsWith("--")||!v||v.startsWith("--")) throw new Error(`Invalid args near ${k??"end"}.`); m.set(k.slice(2),v);} return m; }
function required(m:Map<string,string>,k:string):string { const v=m.get(k)?.trim(); if(!v) throw new Error(`Missing --${k}.`); return v; }
function optional(m:Map<string,string>,k:string):string|undefined { const v=m.get(k)?.trim(); return v||undefined; }
main().catch((e)=>{console.error(e instanceof Error?e.stack??e.message:String(e));process.exitCode=1;});
