"use client";
import { Button, Descriptions, Table } from "antd";
import { RefreshCw } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { StatusTag } from "@/components/common/status-tag";
import { QueryError, PanelSkeleton } from "@/components/common/states";
import { JsonView } from "@/components/common/json-view";
import { useCapabilities, useHealth, useReadiness, useVersion } from "@/lib/query/researchops-hooks";

export default function SystemPage(){
 const health=useHealth(), ready=useReadiness(), version=useVersion(), caps=useCapabilities();
 const error=[health,ready,version,caps].find(x=>x.isError)?.error; const refresh=()=>[health,ready,version,caps].forEach(x=>x.refetch());
 if(error && !ready.data) return <QueryError error={error} onRetry={refresh}/>;
 return <div className="space-y-6"><PageHeader eyebrow="System" title="Control-plane health & identity" description="FastAPI readiness, dependency state, immutable registry identities, API version and exposed capabilities." actions={<Button icon={<RefreshCw size={14}/>} onClick={refresh}>Refresh</Button>}/>
 <section className="grid gap-4 xl:grid-cols-2"><div className="panel p-5"><h2 className="mb-4 text-sm font-semibold">Readiness</h2>{ready.isLoading?<PanelSkeleton/>:<><div className="mb-4"><StatusTag value={ready.data?.ready?"READY":"DEGRADED"}/></div><Table size="small" pagination={false} rowKey="name" dataSource={Object.entries(ready.data?.dependencies||{}).map(([name,v])=>({name,...v}))} columns={[{title:"Dependency",dataIndex:"name"},{title:"Status",dataIndex:"status",render:v=><StatusTag value={v}/>},{title:"Detail",dataIndex:"detail"}]}/></>}</div>
 <div className="panel p-5"><h2 className="mb-4 text-sm font-semibold">Capabilities</h2><Descriptions column={1} size="small" items={caps.data?Object.entries(caps.data).map(([key,value])=>({key,label:key,children:String(value)})):[]}/></div></section>
 <section className="panel p-5"><h2 className="mb-4 text-sm font-semibold">Version & source identities</h2><JsonView value={version.data}/></section></div>
}
