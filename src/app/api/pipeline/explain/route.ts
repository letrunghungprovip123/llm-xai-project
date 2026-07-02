import { NextRequest, NextResponse } from "next/server";
import { runExplanationPipeline } from "@/server/pipeline/explanation-pipeline";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const result = await runExplanationPipeline(body);
    return NextResponse.json(result);
  } catch (error) {
    return NextResponse.json(
      {
        error: "Pipeline failed",
        detail: error instanceof Error ? error.message : String(error),
      },
      { status: 400 },
    );
  }
}
