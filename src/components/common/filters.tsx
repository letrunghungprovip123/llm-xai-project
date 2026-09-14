"use client";
import { Button, Form, Input, Select } from "antd";
import { Filter, RotateCcw } from "lucide-react";

export type FilterField = { name: string; label: string; type?: "text" | "select" | "boolean"; options?: string[] };
export function FilterBar({ fields, value, onChange }: { fields: FilterField[]; value: Record<string, any>; onChange: (v: Record<string, any>) => void }) {
  const [form] = Form.useForm();
  return <div className="panel p-3"><Form form={form} layout="inline" initialValues={value} onFinish={(v)=>onChange(v)} className="gap-y-2!">{fields.map(f => <Form.Item key={f.name} name={f.name} label={f.label} className="mb-0!">{f.type === "select" ? <Select allowClear style={{minWidth:150}} options={(f.options||[]).map(x=>({label:x,value:x}))}/> : f.type === "boolean" ? <Select allowClear style={{minWidth:120}} options={[{label:"True",value:"true"},{label:"False",value:"false"}]}/> : <Input allowClear style={{width:180}}/>}</Form.Item>)}<Form.Item className="mb-0! ml-auto!"><Button htmlType="submit" type="primary" icon={<Filter size={14}/>}>Apply</Button></Form.Item><Form.Item className="mb-0!"><Button icon={<RotateCcw size={14}/>} onClick={()=>{form.resetFields(); fields.forEach(f=>form.setFieldValue(f.name,undefined)); onChange({});}}>Reset</Button></Form.Item></Form></div>;
}
