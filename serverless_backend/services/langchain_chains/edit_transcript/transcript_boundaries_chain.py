from langchain.output_parsers import PydanticOutputParser
from langchain_core.prompts import FewShotPromptTemplate, PromptTemplate
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_openai import ChatOpenAI

model = ChatOpenAI(model_name='gpt-4o')

# Step 1: Determine start and end position
class TranscriptBoundaries(BaseModel):
    start_index: int = Field(description="Start index of the relevant part of the transcript")
    end_index: int = Field(description="End index of the relevant part of the transcript")
    explanation: str = Field(description="Explanation for the chosen boundaries")

transcript_boundaries_parser = PydanticOutputParser(pydantic_object=TranscriptBoundaries)

transcript_boundaries_examples = [
    {
        "transcript": "(0) Hello (1) everyone (2) today (3) we're (4) going (5) to (6) talk (7) about (8) the (9) importance (10) of (11) exercise (12) Regular (13) physical (14) activity (15) is (16) crucial (17) for (18) maintaining (19) good (20) health (21) It (22) helps (23) prevent (24) chronic (25) diseases (26) improves (27) mood (28) and (29) boosts (30) energy (31) levels (32) So (33) let's (34) get (35) started (36) with (37) some (38) simple (39) exercises (40) you (41) can (42) do (43) at (44) home (45) Thank (46) you (47) for (48) watching (49) and (50) stay (51) healthy",
        "short_idea": "Explaining the importance of exercise",
        "response": '{"start_index": 2, "end_index": 44, "explanation": "The chosen segment focuses on the importance of exercise and its benefits, which aligns with the TikTok idea. The introduction and conclusion are trimmed for conciseness."}'
    }
]

transcript_boundaries_prompt = FewShotPromptTemplate(
    examples=transcript_boundaries_examples,
    example_prompt=PromptTemplate(
        input_variables=["transcript", "short_idea", "response"],
        template="Transcript: {transcript}\nTikTok idea: {short_idea}\nResponse: {response}"
    ),
    prefix="Given the transcript and TikTok idea, determine the most relevant start and end indices for the short video:",
    suffix="Now operate on:\nTranscript: {transcript}\nTikTok idea: {short_idea}\n{format_instructions}",
    input_variables=["transcript", "short_idea"],
    partial_variables={"format_instructions": transcript_boundaries_parser.get_format_instructions()},
)

transcript_boundaries_chain = (transcript_boundaries_prompt | model | transcript_boundaries_parser).with_config(
    {"run_name": "Determine Transcript Boundaries", "tags": ["transcript-boundaries"]}
)