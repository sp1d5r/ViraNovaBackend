from langchain.output_parsers import PydanticOutputParser
from langchain_core.prompts import FewShotPromptTemplate, PromptTemplate
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_openai import ChatOpenAI

model = ChatOpenAI(model_name='gpt-4o')

# Step 2: Delete unnecessary segments
class UnnecessarySegments(BaseModel):
    segments: list[tuple[int, int]] = Field(description="List of (start, end) index pairs for segments to be removed")
    explanation: str = Field(description="Explanation for the segments to be removed")

unnecessary_segments_parser = PydanticOutputParser(pydantic_object=UnnecessarySegments)

unnecessary_segments_examples = [
    {
        "transcript": "(0) Today (1) we're (2) going (3) to (4) talk (5) about (6) the (7) importance (8) of (9) exercise (10) Um (11) Regular (12) physical (13) activity (14) is (15) crucial (16) for (17) maintaining (18) good (19) health (20) It (21) helps (22) prevent (23) chronic (24) diseases (25) improves (26) mood (27) and (28) boosts (29) energy (30) levels (31) Like (32) you (33) know",
        "short_idea": "Explaining the importance of exercise",
        "response": '{"segments": [(10, 10), (31, 33)], "explanation": "Removed filler words and phrases (\'Um\' and \'Like you know\') that don\'t contribute to the main idea."}'
    }
]

unnecessary_segments_prompt = FewShotPromptTemplate(
    examples=unnecessary_segments_examples,
    example_prompt=PromptTemplate(
        input_variables=["transcript", "short_idea", "response"],
        template="Transcript: {transcript}\nTikTok idea: {short_idea}\nResponse: {response}"
    ),
    prefix="Given the transcript and TikTok idea, identify unnecessary segments to be removed:",
    suffix="Now operate on:\nTranscript: {transcript}\nTikTok idea: {short_idea}\n{format_instructions}",
    input_variables=["transcript", "short_idea"],
    partial_variables={"format_instructions": unnecessary_segments_parser.get_format_instructions()},
)

unnecessary_segments_chain = (unnecessary_segments_prompt | model | unnecessary_segments_parser).with_config(
    {"run_name": "Identify Unnecessary Segments", "tags": ["unnecessary-segments"]}
)