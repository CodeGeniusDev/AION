from services.gemini import GeminiService


class ResponseSynthesizer:
    async def synthesize(self, message: str, outputs: list[str], model_service: GeminiService) -> str:
        joined = "\n\n".join(outputs)
        prompt = f"User request: {message}\nAgent outputs:\n{joined}\nReturn one final response authored by AION."
        generated = await model_service.generate(
            "Combine verified agent outputs into one concise answer. Never expose private reasoning.",
            prompt,
        )
        if generated:
            return generated
        if outputs:
            # Agent outputs may be live-generated even when this synthesis call
            # failed, so don't label the response "Development mode" here.
            return f"AION coordinated the requested work. {outputs[-1]}"
        return f"Development mode: AION received your request: {message}"

    async def revise(self, message: str, draft: str, model_service: GeminiService) -> str:
        generated = await model_service.generate(
            "Revise the draft once to resolve review concerns. Return only the improved answer.",
            f"Request: {message}\nDraft: {draft}",
        )
        return generated or draft.replace("[needs-revision]", "").strip()

