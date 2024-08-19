from langchain.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_openai import ChatOpenAI

model = ChatOpenAI(model_name='gpt-4o')

class TikTokTitle(BaseModel):
    short_title_top: str = Field(description="Top line of the TikTok title")
    short_title_bottom: str = Field(description="Bottom line of the TikTok title")

title_generator_parser = PydanticOutputParser(pydantic_object=TikTokTitle)

title_generator_prompt = PromptTemplate(
    template="You are a TikTok title generator. Create a catchy two-line title based on the given idea and transcript segment. The title should be attention-grabbing and relevant to the content. Here's the TikTok idea: {tiktok_idea}\n\nHere's the transcript segment: {segment_transcript}\n\n{format_instructions}",
    input_variables=["tiktok_idea", "segment_transcript"],
    partial_variables={"format_instructions": title_generator_parser.get_format_instructions()},
)

title_generator_chain = (title_generator_prompt | model | title_generator_parser).with_config({"run_name": "TikTok Title Generator", "tags": ["tiktok-title-generator"]})