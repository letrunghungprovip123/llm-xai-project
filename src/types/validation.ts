  export type ValidationErrorItem = {
    type: string;
    message: string;
  };

  export type ValidationResult = {
    status: "passed" | "failed";
    faithfulnessScore: number;
    errors: ValidationErrorItem[];
    feedback: string | null;
  };
