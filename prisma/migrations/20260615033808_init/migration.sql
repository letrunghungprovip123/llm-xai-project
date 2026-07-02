-- CreateTable
CREATE TABLE "Customer" (
    "id" TEXT NOT NULL,
    "externalId" TEXT,
    "payload" JSONB NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Customer_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Prediction" (
    "id" TEXT NOT NULL,
    "customerId" TEXT,
    "modelName" TEXT NOT NULL,
    "modelVersion" TEXT NOT NULL,
    "predictedLabel" TEXT NOT NULL,
    "probability" DOUBLE PRECISION NOT NULL,
    "threshold" DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    "inputPayload" JSONB NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Prediction_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ExplanationIR" (
    "id" TEXT NOT NULL,
    "predictionId" TEXT NOT NULL,
    "irVersion" TEXT NOT NULL,
    "irJson" JSONB NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ExplanationIR_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "LLMExplanation" (
    "id" TEXT NOT NULL,
    "predictionId" TEXT NOT NULL,
    "audienceType" TEXT NOT NULL,
    "promptVersion" TEXT NOT NULL,
    "llmModel" TEXT NOT NULL,
    "text" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "LLMExplanation_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ValidationResult" (
    "id" TEXT NOT NULL,
    "explanationId" TEXT NOT NULL,
    "status" TEXT NOT NULL,
    "faithfulnessScore" DOUBLE PRECISION NOT NULL,
    "errorsJson" JSONB NOT NULL,
    "feedback" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ValidationResult_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "HumanEvaluation" (
    "id" TEXT NOT NULL,
    "explanationId" TEXT NOT NULL,
    "evaluatorType" TEXT,
    "clarityScore" INTEGER,
    "usefulnessScore" INTEGER,
    "trustScore" INTEGER,
    "correctnessScore" INTEGER,
    "comment" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "HumanEvaluation_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "Customer_externalId_key" ON "Customer"("externalId");

-- AddForeignKey
ALTER TABLE "Prediction" ADD CONSTRAINT "Prediction_customerId_fkey" FOREIGN KEY ("customerId") REFERENCES "Customer"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ExplanationIR" ADD CONSTRAINT "ExplanationIR_predictionId_fkey" FOREIGN KEY ("predictionId") REFERENCES "Prediction"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "LLMExplanation" ADD CONSTRAINT "LLMExplanation_predictionId_fkey" FOREIGN KEY ("predictionId") REFERENCES "Prediction"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ValidationResult" ADD CONSTRAINT "ValidationResult_explanationId_fkey" FOREIGN KEY ("explanationId") REFERENCES "LLMExplanation"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "HumanEvaluation" ADD CONSTRAINT "HumanEvaluation_explanationId_fkey" FOREIGN KEY ("explanationId") REFERENCES "LLMExplanation"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
