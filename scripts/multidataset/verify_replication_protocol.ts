import { REPLICATION_PROTOCOL, assertReplicationProtocolMatchesCommonRuntime, replicationProtocolSha256 } from "../../research/ts/replication/protocol";

function main(): void {
  assertReplicationProtocolMatchesCommonRuntime();
  const models = REPLICATION_PROTOCOL.generation.models.map((item) => item.model_id).join(",");
  console.log(`PASS protocol_id=${REPLICATION_PROTOCOL.protocol_id}`);
  console.log(`PASS models=${models}`);
  console.log(`PASS prompt_version=${REPLICATION_PROTOCOL.generation.prompt_version} output_schema=${REPLICATION_PROTOCOL.generation.output_schema_version}`);
  console.log(`PASS planned=${REPLICATION_PROTOCOL.generation.matrix.planned_generations} historical_home_credit_usable_reference=${REPLICATION_PROTOCOL.source_experiment.historical_usable_generations}`);
  console.log(`REPLICATION_PROTOCOL_SHA256=${replicationProtocolSha256()}`);
  console.log("REPLICATION_PROTOCOL_FREEZE=PASS");
}

try { main(); } catch (error) {
  console.error(error instanceof Error ? error.stack ?? error.message : String(error));
  process.exitCode = 1;
}
