import Link from "next/link";

export default function HomePage() {
  return (
    <main className="min-h-screen p-8">
      <h1 className="text-3xl font-bold">
        LLM-XAI Trustworthy Explanation System
      </h1>

      <p className="mt-4 text-gray-600">
        Prototype for XAI evidence, LLM explanation, validation, and
        self-refinement.
      </p>

      <Link
        href="/dashboard/explanations"
        className="mt-6 inline-block rounded bg-black px-4 py-2 text-white"
      >
        Open Explanation Dashboard
      </Link>
    </main>
  );
}
