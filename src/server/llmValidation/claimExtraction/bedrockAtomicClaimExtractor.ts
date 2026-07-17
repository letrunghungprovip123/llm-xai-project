/**
 * File tương thích tạm thời cho dự án đã cài bản v2 dùng Bedrock.
 * Toàn bộ runtime bên dưới đã chuyển sang DeepSeek, không còn gọi AWS.
 */
export {
  ClaimResponseJsonError as BedrockResponseJsonError,
  DEEPSEEK_EXTRACTOR_LINEAGE as BEDROCK_EXTRACTOR_LINEAGE,
  DeepSeekAtomicClaimExtractor as BedrockAtomicClaimExtractor,
  getDefaultDeepSeekAtomicClaimExtractorConfig as getDefaultBedrockAtomicClaimExtractorConfig,
  parseClaimExtractionResponse,
} from "./deepseekAtomicClaimExtractor";

export type {
  DeepSeekAtomicClaimExtractorConfig as BedrockAtomicClaimExtractorConfig,
} from "./deepseekAtomicClaimExtractor";
