from langchain.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.pydantic_v1 import BaseModel, Field, validator
from langchain_openai import ChatOpenAI

model = ChatOpenAI(model_name='gpt-3.5-turbo-16k')

class DeleteOperation(BaseModel):
    start_index: int = Field(description="Start index of sequence to delete")
    end_index: int = Field(description="End index of sequence to delete")
    explanation: str = Field(description="Explanation of why we're deleting this sequence")

    @validator("start_index", "end_index")
    def index_must_be_positive(cls, value):
        if value < 0:
            raise ValueError("Index must be non-negative")
        return value

delete_operation_parser = PydanticOutputParser(pydantic_object=DeleteOperation)

delete_operation_prompt = PromptTemplate(
    template="Given the transcript {transcript}, and the TikTok idea:\n{short_idea}\n\n Decide which section of the transcript needs to be deleted because it is unrelated to the TikTok idea. Avoid being over agressive with the cropping. Remember if you see (-1) you've already deleted that word.\n\n Follow the output schema and return a single json. The transcript should still make sense. \n\n  {format_instructions}",
    input_variables=["transcript", "short_idea"],
    partial_variables={"format_instructions": delete_operation_parser.get_format_instructions()},
)

delete_operation_chain = (delete_operation_prompt | model | delete_operation_parser).with_config({"run_name": "Perform Delete Operation", "tags": ["delete-operation"]})


class RequiresCropping(BaseModel):
    requires_cropping: bool = Field(description="Boolean field deciding if transcript needs to be reduced in size.")
    explanation: str = Field(description="An explanation for why we need to continue cropping.")


requires_cropping_parser = PydanticOutputParser(pydantic_object=RequiresCropping)

requires_cropping_prompt = PromptTemplate(
    template="Given the transcript {transcript}, and the tiktok idea: {short_idea} \n\n Decide if the transcript needs to be reduced in size, remember the transcript needs to be understandable - primarily look for text that's unrelated to the tiktok idea we are trying to produce. Don't be over aggressive with cropping, return false if transcript is getting too small (less than 100 words...). Always give an explanation: \n\n {format_instructions}",
    input_variables=["transcript", "short_idea"],
    partial_variables={"format_instructions": requires_cropping_parser.get_format_instructions()},
)

requires_cropping_chain = (requires_cropping_prompt | model | requires_cropping_parser).with_config({"run_name": "Requires Cropping", "tags": ["check-requires-cropping"]})

