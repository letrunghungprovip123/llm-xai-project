"use client";
import { Tabs, Table } from "antd";
import { PageHeader } from "@/components/common/page-header";
import { StatusTag } from "@/components/common/status-tag";
import { JsonView } from "@/components/common/json-view";
import { QueryError } from "@/components/common/states";
import { useDeployments, useFlows, useStages } from "@/lib/query/researchops-hooks";

export default function RegistryPage(){ const stages=useStages(),flows=useFlows(),deployments=useDeployments(); const error=[stages,flows,deployments].find(q=>q.isError)?.error; if(error)return <QueryError error={error}/>; const render=(data:any[]=[])=><Table rowKey="id" size="small" pagination={false} dataSource={data} expandable={{expandedRowRender:r=><JsonView value={r.metadata} maxHeight={240}/>}} columns={[{title:"Status",dataIndex:"status",width:130,render:v=><StatusTag value={v}/>},{title:"ID",dataIndex:"id"},{title:"Version",dataIndex:"version",width:100},{title:"Title",dataIndex:"title"},{title:"Description",dataIndex:"description"}]}/>; return <div className="space-y-6"><PageHeader eyebrow="Registry" title="Stage, flow & deployment registry" description="Read-only registry views from the FastAPI control plane. Git-backed identities remain authoritative."/><div className="panel px-4 pb-4"><Tabs items={[{key:"stages",label:`Stages (${stages.data?.length||0})`,children:render(stages.data)},{key:"flows",label:`Flows (${flows.data?.length||0})`,children:render(flows.data)},{key:"deployments",label:`Deployments (${deployments.data?.length||0})`,children:render(deployments.data)}]}/></div></div> }
