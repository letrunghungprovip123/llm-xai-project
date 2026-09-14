"use client";

import { useEffect, useState } from "react";
import { Form, Input, Modal } from "antd";
import { newCommandId } from "@/lib/api/client";

export function ReasonCommandModal({ open, title, confirmText, danger, loading, onCancel, onSubmit, children }: {
  open: boolean; title: string; confirmText: string; danger?: boolean; loading?: boolean; onCancel: () => void;
  onSubmit: (reason: string, idempotencyKey: string) => Promise<void> | void; children?: React.ReactNode;
}) {
  const [form] = Form.useForm();
  const [key, setKey] = useState(newCommandId());
  useEffect(() => { if (open) { setKey(newCommandId()); form.resetFields(); } }, [open, form]);
  return <Modal open={open} title={title} okText={confirmText} okButtonProps={{ danger }} confirmLoading={loading} onCancel={onCancel} onOk={async () => { const values = await form.validateFields(); await onSubmit(values.reason, key); }} destroyOnHidden>
    <div className="mb-4 text-sm text-[var(--muted)]">Command ID <code>{key}</code>. Retries inside this command reuse the same idempotency identity.</div>
    {children}
    <Form form={form} layout="vertical"><Form.Item name="reason" label="Reason" rules={[{ required: true, whitespace: true, message: "A reason is required" }]}><Input.TextArea rows={4} maxLength={4000} showCount /></Form.Item></Form>
  </Modal>;
}
