from langchain.output_parsers import PydanticOutputParser
from langchain_core.prompts import FewShotPromptTemplate, PromptTemplate
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_openai import ChatOpenAI

model = ChatOpenAI(model_name='gpt-4o')

# Step 3: Find the hook
class Hook(BaseModel):
    start_index: int = Field(description="Start index of the hook")
    end_index: int = Field(description="End index of the hook")
    explanation: str = Field(description="Explanation for why this is a good hook")

hook_parser = PydanticOutputParser(pydantic_object=Hook)

hook_examples = [
    {
        "transcript": "(0) Today (1) we're (2) going (3) to (4) talk (5) about (6) the (7) importance (8) of (9) exercise (10) Regular (11) physical (12) activity (13) is (14) crucial (15) for (16) maintaining (17) good (18) health (19) It (20) helps (21) prevent (22) chronic (23) diseases (24) improves (25) mood (26) and (27) boosts (28) energy (29) levels",
        "short_idea": "Explaining the importance of exercise",
        "response": '{"start_index": 10, "end_index": 18, "explanation": "This segment succinctly captures the main idea and benefits of exercise, making it an engaging hook for the video."}'
    }
]

hook_prompt = FewShotPromptTemplate(
    examples=hook_examples,
    example_prompt=PromptTemplate(
        input_variables=["transcript", "short_idea", "response"],
        template="Transcript: {transcript}\nTikTok idea: {short_idea}\nResponse: {response}"
    ),
    prefix="Given the transcript and TikTok idea, identify the most captivating hook:",
    suffix="Now operate on:\nTranscript: {transcript}\nTikTok idea: {short_idea}\n{format_instructions}",
    input_variables=["transcript", "short_idea"],
    partial_variables={"format_instructions": hook_parser.get_format_instructions()},
)

hook_chain = (hook_prompt | model | hook_parser).with_config(
    {"run_name": "Find Hook", "tags": ["find-hook"]}
)