import os
import datetime
from dotenv import load_dotenv
from pydantic import BaseModel
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
checkpoint = InMemorySaver()

class StockInput(BaseModel):
    ticker: str

class StockHistoryInput(StockInput):
    start_date: str
    end_date: str

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

    try:
        # Convert ANY input date → YYYY-MM-DD
        start_date = datetime.strptime(start_date.replace("/", "-"), "%Y-%m-%d").strftime("%Y-%m-%d")
        end_date = datetime.strptime(end_date.replace("/", "-"), "%Y-%m-%d").strftime("%Y-%m-%d")
    except:
        return "Invalid date format. Use YYYY-MM-DD (example: 2020-01-01)."

    stock = yf.Ticker(ticker)
    df = stock.history(start=start_date, end=end_date)

    if df.empty:
        return f"No historical data found for {ticker}"

    # return df.to_string()
    return df

@tool('get_balance_sheet',args_schema=StockInput, description='A function that returns the balance sheet based on a ticker symbol.')
def get_balance_sheet(ticker: str):
    print("get_balance_sheet tool is being used")

    try:
        stock = yf.Ticker(ticker)
        bs = stock.balance_sheet

        if bs.empty:
            return f"No balance sheet found for {ticker}"

        latest = bs.iloc[:, 0]

        return f"""
    Balance Sheet Highlights for {ticker}:

    Total Debt: {latest.get('Total Debt')}
    Net Debt: {latest.get('Net Debt')}
    Cash & Cash Equivalents: {latest.get('Cash And Cash Equivalents')}
    Total Assets: {latest.get('Total Assets')}
    Shareholder Equity: {latest.get('Stockholders Equity')}
    """

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
            link = n.get("link") or ""
            headlines.append(f"{title}\n{link}")

        return "\n\n".join(headlines)

    except Exception as e:
        return f"Error fetching news for {ticker}: {str(e)}"

model=ChatGroq(
    model=os.getenv("GROQ_MODEL")
    ,
    streaming=True
)

agent =create_agent(model=model,
                    tools=[
                        get_stock_price,
                        get_historical_stock_price,
                        get_balance_sheet,
                        get_stock_news
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
            You are a stock analysis assistant.

            When using tools:
            - Always call tools with correct arguments
            - Always produce a final natural language answer after tool use
            - Never stop after tool execution
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
    uvicorn.run(app, host="0.0.0.0", port=8000)
    # print("RELIANCE:\n", yf.Ticker("TMCV.NS").history(period="1d"))
