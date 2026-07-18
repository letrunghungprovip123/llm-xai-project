"use client";

import { useState } from "react";

type PipelineResult = {
  explanation?: { text?: string };
  validation?: unknown;
  ir?: unknown;
};

export default function ExplanationDashboardPage() {
  const [result, setResult] = useState<PipelineResult | null>(null);
  const [loading, setLoading] = useState(false);

  async function runPipeline() {
    setLoading(true);

    try {
      const response = await fetch("/api/pipeline/explain", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          customer: {
            age: 34,
            job: "admin.",
            education: "university.degree",
            poutcome: "success",
          },
          audience: "marketing",
        }),
      });

      const data = (await response.json()) as PipelineResult;
      setResult(data);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen p-8">
      <h1 className="text-2xl font-bold">Explanation Pipeline Demo</h1>

      <button
        onClick={runPipeline}
        disabled={loading}
        className="mt-4 rounded bg-black px-4 py-2 text-white disabled:opacity-50"
      >
        {loading ? "Running..." : "Run Mock Pipeline"}
      </button>

      <section className="mt-6 rounded border p-4">
        <h2 className="text-xl font-semibold">Natural Language Explanation</h2>
        <p className="mt-2">
          {result?.explanation?.text ?? "No explanation yet."}
        </p>
      </section>

      <section className="mt-6 rounded border p-4">
        <h2 className="text-xl font-semibold">Validation</h2>
        <pre className="mt-2 overflow-auto bg-gray-100 p-4 text-sm">
          {result
            ? JSON.stringify(result.validation, null, 2)
            : "No validation yet."}
        </pre>
      </section>

      <section className="mt-6 rounded border p-4">
        <h2 className="text-xl font-semibold">Explanation IR</h2>
        <pre className="mt-2 max-h-[500px] overflow-auto bg-gray-100 p-4 text-sm">
          {result ? JSON.stringify(result.ir, null, 2) : "No IR yet."}
        </pre>
      </section>
    </main>
  );
}
