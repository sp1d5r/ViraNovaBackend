from langchain.output_parsers import PydanticOutputParser
from langchain_core.prompts import FewShotPromptTemplate, PromptTemplate
from langchain_core.pydantic_v1 import BaseModel, Field, validator
from langchain_openai import ChatOpenAI

model = ChatOpenAI(model_name='gpt-4o')



"""

DELETE OPERATION WITH EXAMPLES:

"""

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

examples = [
    {
        "transcript": "(0) big (1) man (2) thing (3) yeah (4) bra (5) as (6) some (7) of (8) you (9) lot (10) know (11) already (12) I (13) won (14) this (15) season (16) of (17) inside (18) BR (19) in (20) fact (21) I'm (22) already (23) spending (24) the (25) money (26) bro (27) I (28) went (29) and (30) coped (31) a (32) new (33) whip (34) BR (35) went (36) to (37) got (38) a (39) Range (40) Rover (41) M (42) but (43) yeah (44) real (45) talk (46) though (47) big (48) up (49) the (50) side (51) men (52) brao (53) well (54) done (55) to (56) them (57) for (58) putting (59) on (60) the (61) best (62) reality (63) show (64) ever (65) bro (66) and (67) I'm (68) glad (69) that (70) I (71) was (72) a (73) part (74) of (75) it (76) big (77) up (78) all (79) the (80) production (81) big (82) up (83) everybody (84) involved (85) in (86) making (87) it (88) the (89) cost (90) everybody (91) and (92) big (93) up (94) all (95) the (96) sidemen (97) fans (98) bro (99) cuz (100) you (101) guys (102) have (103) been (104) amazing (105) bro (106) like (107) I (108) said (109) I'm (110) very (111) grateful (112) and (113) blessed (114) to (115) be (116) a (117) part (118) of (119) the (120) show (121) bro (122) so (123) big (124) up (125) to (126) side (127) man (128) thank (129) you (130) inside (131) bro (132) now (133) my (134) reasons (135) for (136) going (137) in (138) the (139) show (140) bro (141) I'm (142) not (143) going (144) to (145) lie (146) to (147) you (148) bra (149) I (150) was (151) just (152) going (153) in (154) there (155) for (156) Vibes (157) I (158) thought (159) it's (160) a (161) weak (162) holiday (163) man's (164) going (165) to (166) go (167) in (168) there (169) jam (170) with (171) some",
        "short_idea": "Celebrating winning Inside BR",
        "response": '{{"start_index": 133,"end_index": 171,"explanation": "This section discusses the reason for entering the show, which is unrelated to the TikTok idea of celebrating winning Inside BR."}}'
    },
    {
        "transcript": "(0) working (1) hard (2) keep (3) begging (4) it (5) keep (6) asking (7) deji (8) keep (9) getting (10) aired (11) and (12) finally (13) you'll (14) get (15) here (16) my (17) name (18) is (19) Harry (20) Panero (21) yes (22) yes (23) yes (24) and (25) and (26) my (27) my (28) advice (29) to (30) the (31) youth (32) is (33) where's (34) my (35) camera (36) right (37) here (38) my (39) advice (40) to (41) the (42) youth (43) is (44) run (45) with (46) scissors (47) yeah (48) piss (49) in (50) the (51) wind (52) you (53) what (54) I (55) mean (56) you (57) only (58) live (59) once (60) and (61) you (62) want (63) to (64) you (65) what (66) I (67) mean (68) mhm (69) just (70) what (71) does (72) pissing (73) the (74) wind (75) mean (76) um (77) it's (78) pretty (79) self-explanatory (80) what (81) you (82) want (83) to (84) do (85) is (86) you (87) pull (88) your (89) you (90) pull (91) your (92) plunker (93) whoa (94) whoa (95) okay (96) Dum (97) it (98) down (99) D (100) it (101) down (102) no (103) no (104) but (105) no (106) but (107) why (108) but (109) clearly (110) there (111) must (112) be (113) a (114) meaning (115) behind (116) it (117) like (118) yeah (119) you (120) don't (121) you (122) don't (123) piss (124) in (125) the (126) wind (127) in (128) life (129) just (130) let (131) things (132) happen (133) it's (134) pissing (135) in (136) the (137) wind (138) smart (139) but (140) what (141) is (142) pissing (143) in (144) the (145) wind (146) it's (147) when (148) you (149) piss (150) in (151) the (152) [\xa0__\xa0] (153) wind (154) oh (155) what (156) no (157) so (158) you (159) just (160) spray (161) people (162) what (163) with (164) your (165) P (166) okay (167) I (168) need (169) I (170) need (171) I",
        "short_idea": "Explaining the phrase 'pissing in the wind'",
        "response": '{{"start_index": 0,"end_index": 16,"explanation": "This section discusses working hard and getting aired, which is unrelated to the TikTok idea of explaining the phrase \'pissing in the wind.\'"}}'

    }
]

example_prompt = PromptTemplate(
    input_variables=["transcript", "short_idea", "response"],
    template="""
    Transcript: {transcript}
    TikTok idea: {short_idea}
    Response: {response}
    """
)

# Create FewShotPromptTemplate
delete_operation_prompt = FewShotPromptTemplate(
    examples=examples,
    example_prompt=example_prompt,
    prefix="Given the transcript and the TikTok idea, decide which section of the transcript needs to be deleted because it is unrelated to the TikTok idea. Avoid being over aggressive with the cropping. Remember if you see (-1) you've already deleted that word.\n\nFollow the output schema and return a single json. The transcript should still make sense.\n\nHere are some examples:",
    suffix="Now operate on: Transcript: {transcript}\nTikTok idea: {short_idea}\n{format_instructions}",
    input_variables=["transcript", "short_idea"],
    partial_variables={"format_instructions": delete_operation_parser.get_format_instructions()},
)

delete_operation_chain = (delete_operation_prompt | model | delete_operation_parser).with_config(
    {"run_name": "Perform Delete Operation", "tags": ["delete-operation"]})


"""
REQUIRES CROPPING WITH EXAMPLES:
"""

class RequiresCropping(BaseModel):
    requires_cropping: bool = Field(description="Boolean field deciding if transcript needs to be reduced in size.")
    explanation: str = Field(description="An explanation for why we need to continue cropping.")


requires_cropping_parser = PydanticOutputParser(pydantic_object=RequiresCropping)

requires_cropping_examples = [
    {
        "transcript": "big man thing yeah bra as some of you lot know already I won this season of inside BR in fact I'm already spending the money bro I went and coped a new whip BR went to got a Range Rover M but yeah real talk though big up the side men brao well done to them for putting on the best reality show ever bro and I'm glad that I was a part of it big up all the production big up everybody involved in making it the cost everybody and big up all the sidemen fans bro cuz you guys have been amazing bro like I said I'm very grateful and blessed to be a part of the show bro so big up to side man thank you inside bro",
        "short_idea": "Celebrating winning Inside BR",
        "response": '{{ "requires_cropping": False, "explanation": "The transcript contains all the necessary content to the idea of \'Celebrating winning Inside BR\', such as where the contestant spent their money and gratitude for the opportunity."}}'
    },
    {
        "transcript": "working hard keep begging it keep asking deji keep getting aired and finally you'll get here my name is Harry Panero yes yes yes and and my my advice to the youth is where's my camera right here my advice to the youth is run with scissors yeah piss in the wind you what I mean you only live once and you want to you what I mean mhm just what does pissing the wind mean um it's pretty self-explanatory what you want to do is you pull your you pull your plunker whoa whoa okay Dum it down D it down no no but no but why but clearly there must be a meaning behind it like yeah you don't you don't piss in the wind in life just let things happen it's pissing in the wind smart but what is pissing in the wind it's when you piss in the [\xa0__\xa0] wind oh what no so you just spray people what with your P okay I need I need I",
        "short_idea": "Explaining the phrase 'pissing in the wind'",
        "response": '{{ "requires_cropping": True, "explanation": "The transcript contains a significant amount of unrelated content at the beginning, such as \'working hard keep begging it keep asking deji keep getting aired and finally you\'ll get here\', which does not contribute to the explanation of the phrase \'pissing in the wind\'. Removing this portion would make the transcript more focused and understandable for the TikTok idea."}}'
    },
    {
        "transcript": "my name is Harry Panero yes yes yes and and my my advice to the youth is where's my camera right here my advice to the youth is run with scissors yeah piss in the wind you what I mean you only live once and you want to you what I mean mhm just what does pissing the wind mean um it's pretty self-explanatory what you want to do is you pull your you pull your plunker whoa whoa okay Dum it down D it down no no but no but why but clearly there must be a meaning behind it like yeah you don't you don't piss in the wind in life just let things happen it's pissing in the wind smart but what is pissing in the wind it's when you piss in the [\xa0__\xa0] wind oh what no so you just spray people what with your P okay I need I need",
        "short_idea": "Explaining the phrase 'pissing in the wind'",
        "response": '{{ "requires_cropping": False, "explanation": "Transcript is funny and contains all the necessary information to make an entertaining short."}}'

    }
]

requires_cropping_example_prompt = PromptTemplate(
    input_variables=["transcript", "short_idea", "response"],
    template="""
    Transcript: {transcript}
    TikTok idea: {short_idea}
    Response: {response}
    """
)

# Create FewShotPromptTemplate
requires_cropping_prompt = FewShotPromptTemplate(
    examples=requires_cropping_examples,
    example_prompt=requires_cropping_example_prompt,
    prefix="Given the transcript {transcript}, and the tiktok idea: {short_idea} \n\n Decide if the transcript needs to be reduced in size, remember the transcript needs to be understandable - primarily look for text that's unrelated to the tiktok idea we are trying to produce unless that text provides entertainment value. Don't be over aggressive with cropping, return false if transcript is getting too small (less than 100 words...). \n\nHere are some examples:",
    suffix="Now operate on: Transcript: {transcript}\nTikTok idea: {short_idea}\n{format_instructions}",
    input_variables=["transcript", "short_idea"],
    partial_variables={"format_instructions": requires_cropping_parser.get_format_instructions()},
)

requires_cropping_chain = (requires_cropping_prompt | model | requires_cropping_parser).with_config(
    {"run_name": "Requires Cropping", "tags": ["check-requires-cropping"]})