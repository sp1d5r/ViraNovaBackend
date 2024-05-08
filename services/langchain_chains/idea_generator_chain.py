from langchain.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.pydantic_v1 import BaseModel, Field, validator
from langchain_openai import ChatOpenAI

model = ChatOpenAI(model_name='gpt-3.5-turbo-16k')

class TikTokIdea(BaseModel):
    tiktok_idea: str = Field(description="Idea for a tiktok, using the transcript.")
    explanation: str = Field(description="Why you've chosen this idea from the transcript.")


idea_generator_parser = PydanticOutputParser(pydantic_object=TikTokIdea)

idea_generator_prompt = PromptTemplate(
    template="You are a tiktok generator. You take in a subsection fo a transcript and determine a sub-transcript idea you could create using only the existing transcript. You have no access to additional words so only give tiktok ideas that can create tiktok's using the existing transcript (this might involve deleteing words etc) If you can't come up with an idea leave the tiktok_idea field blank. Here's the transcript {transcript} \n\n  {format_instructions}",
    input_variables=["transcript", "short_idea"],
    partial_variables={"format_instructions": idea_generator_parser.get_format_instructions()},
)

idea_generator_chain = idea_generator_prompt | model | idea_generator_parser
