import os
from datetime import datetime
from dotenv import load_dotenv
from pydantic import BaseModel, field_validator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
# from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain.agents import create_agent
from langchain.tools import tool
from langchain.messages import SystemMessage, HumanMessage
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.runnables import RunnableConfig
import yfinance as yf
from langchain.memory import ConversationBufferWindowMemory
# from langgraph.graph import MessagesState
import uvicorn
load_dotenv()
app=FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# checkpoint = InMemorySaver()
checkpoint = ConversationBufferWindowMemory(k=4)

class StockInput(BaseModel):
    ticker: str

class StockHistoryInput(StockInput):
    start_date: str
    end_date: str

    # ---------- PARSE & VALIDATE DATE ----------
    @field_validator("start_date", "end_date")
    @classmethod
    def validate_date_format(cls, value: str):
        formats = [
            "%Y-%m-%d",  # 2024-01-01
            "%d-%m-%Y",  # 01-01-2024
            "%d/%m/%Y",  # 01/01/2024
            "%m/%d/%Y",  # 01/01/2024
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(value.strip(), fmt)
                return dt.strftime("%Y-%m-%d")  # normalize to YYYY-MM-DD
            except ValueError:
                continue

        raise ValueError(
            "Invalid date format. Use YYYY-MM-DD (example: 2024-01-01)"
        )

    # ---------- START < END VALIDATION ----------
    @field_validator("end_date")
    @classmethod
    def validate_date_order(cls, end_date, info):
        start_date = info.data.get("start_date")

        if start_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")

            if start_dt > end_dt:
                raise ValueError("start_date must be before end_date")

        return end_date


LAST_TOOL_OUTPUT = {}

@tool(name_or_callable="get_stock_price" , args_schema=StockInput ,description='A function that returns the current stock price based on a ticker symbol.')
def get_stock_price(ticker: str):
    print("get_stock_price tool is being used")

    ticker = ticker.strip().upper()
    stock = yf.Ticker(ticker)
    df = stock.history(period="5d")

    if df is None or df.empty:
        return f"No price data available for {ticker}"

    price = float(df["Close"].dropna().iloc[-1])
    return f"The current stock price of {ticker} is {price}"

@tool('get_historical_stock_price',args_schema=StockHistoryInput, description='A function that returns the current stock price over time based on a ticker symbol and a start and end date.')
def get_historical_stock_price(ticker: str, start_date: str, end_date: str):
    print("get_historical_stock_price tool is being used")


    stock = yf.Ticker(ticker)
    df = stock.history(start=start_date, end=end_date)

    if df.empty:
        return f"No historical data found for {ticker}"

    result = df.to_string()
    LAST_TOOL_OUTPUT["history"] = result
    return result

@tool('get_balance_sheet',args_schema=StockInput, description='A function that returns the balance sheet based on a ticker symbol.')
def get_balance_sheet(ticker: str):
    print("get_balance_sheet tool is being used")

    try:
        stock = yf.Ticker(ticker)
        bs = stock.balance_sheet

        if bs.empty:
            return f"No balance sheet found for {ticker}"

        bs = stock.balance_sheet

        summary = {
            "Total Debt": bs.loc["Total Debt"].iloc[0],
            "Net Debt": bs.loc["Net Debt"].iloc[0],
            "Cash": bs.loc["Cash And Cash Equivalents"].iloc[0],
            "Total Assets": bs.loc["Total Assets"].iloc[0],
            "Equity": bs.loc["Total Stockholder Equity"].iloc[0]
        }

        return str(summary)

    except Exception as e:
        return f"Error fetching balance sheet: {str(e)}"

@tool('get_stock_news',args_schema=StockInput, description='A function that returns news based on a ticker symbol.')
def get_stock_news(ticker: str):
    print("get_stock_news tool is being used")

    try:
        stock = yf.Ticker(ticker)
        news = stock.news

        if not news:
            return f"No news found for {ticker}"

        headlines = []
        for n in news[:5]:
            title = n.get("title") or n.get("headline") or "No title"
            headlines.append(title)

        return "NEWS_HEADLINES:\n" + "\n".join(headlines)

    except Exception as e:
        return f"Error fetching news for {ticker}: {str(e)}"


@tool(name_or_callable="show_last_history" , description='A function that returns the last historical stock price based on a ticker symbol.')
def show_last_history():
    return LAST_TOOL_OUTPUT.get("history", "No previous history available")

model=ChatGroq(
    model=os.getenv("GROQ_MODEL")
    ,
    streaming=True,
    temperature=0
)

agent =create_agent(model=model,
                    tools=[
                        get_stock_price,
                        get_historical_stock_price,
                        get_balance_sheet,
                        get_stock_news,
                        show_last_history
                    ],
                    checkpointer=checkpoint)

class PromptObject(BaseModel):
    content: str
    id: str
    role: str


class RequestObject(BaseModel):
    prompt: PromptObject
    threadId: str
    responseId: str

@app.post("/api/chat")
async def chat(request: RequestObject):
    config = RunnableConfig(configurable= {"thread_id": request.threadId})

    state = {
        "messages": [
            SystemMessage(content="""
            You are a stock analysis assistant WITH REAL-TIME TOOL ACCESS.

            You MUST use tool results in your final answer.

            STRICT RULES:

            - You DO have access to real-time data.
            - NEVER say you cannot access real-time information.
            - NEVER give generic answers when a ticker is present.
            - ALWAYS USE tool output to generate the answer.
            - If tool returns headlines → show headlines.
            - If tool returns table → show table.
            - NEVER ignore tool output.
            - NEVER suggest Google or other websites.
            - NEVER refuse.

            INTENT RULES:

            1. "news about <ticker>"
               → CALL get_stock_news
               → Return ONLY news headlines from tool output.

            2. "tell me about <ticker>"
               → CALL get_stock_price + get_balance_sheet
               → Return summary USING tool data.

            3. "history"
               → CALL get_historical_stock_price
               → Show table EXACTLY from tool.

            4. "detail" / "analysis"
               → CALL get_stock_price + get_balance_sheet + get_stock_news
               → Return detailed explanation USING tool data.

            If tool output is empty:
            → Say "No data available for <ticker>"

            NEVER ignore tool results.
            NEVER hallucinate.
            """),
            HumanMessage(content=request.prompt.content)
        ]
    }

    # async def generate():
    #     final_text = ""
    #
    #     async for event in agent.astream(
    #             state,
    #             config=config,
    #             stream_mode="messages"
    #     ):
    #         if isinstance(event, dict) and "messages" in event:
    #             msg = event["messages"][-1]
    #
    #             if msg.type == "ai" and msg.content:
    #                 print("STREAM:", msg.content)
    #                 final_text += msg.content
    #                 yield msg.content
    #
    #     # 🔴 IMPORTANT: If model never streamed final answer, send fallback
    #     if not final_text:
    #         yield "I fetched the data but could not generate a response. Please try again."
    #
    # return StreamingResponse(
    #     generate(),
    #     media_type="text/plain",
    #     headers={
    #         "Cache-Control": "no-cache",
    #         "Connection": "keep-alive",
    #     },
    # )
    result = await agent.ainvoke({
        "messages": [
            SystemMessage(content="You are a stock assistant."),
            HumanMessage(content=request.prompt.content)
        ]
    },
    config=config)
    print({"response": result["messages"][-1].content})
    return {"response": result["messages"][-1].content}

if __name__ == '__main__':
    port=os.environ.get("PORT",8000)
    uvicorn.run(app, host="0.0.0.0", port=port)
    # print("RELIANCE:\n", yf.Ticker("TMCV.NS").history(period="1d"))
