import os

from dotenv import load_dotenv
from pydantic import BaseModel
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain.agents import create_agent
from langchain.tools import tool
from langchain.messages import SystemMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import InMemorySaver
import yfinance as yf

load_dotenv()
app=FastAPI()
checkpoint = InMemorySaver()

class StockInput(BaseModel):
    ticker: str

class StockHistoryInput(StockInput):
    start_date: str
    end_date: str

@tool(name_or_callable="get_stock_price" , args_schema=StockInput ,description='A function that returns the current stock price based on a ticker symbol.')
def get_stock_price(ticker: str):
    print("get print price tool is being used")
    stock=yf.Ticker(ticker)
    return stock.history()["Close"].iloc[-1]

@tool('get_historical_stock_price',args_schema=StockHistoryInput, description='A function that returns the current stock price over time based on a ticker symbol and a start and end date.')
def get_historical_stock_price(ticker: str, start_date: str, end_date: str):
    print('get_historical_stock_price tool is being used')
    stock = yf.Ticker(ticker)
    return stock.history(start=start_date, end=end_date).to_dict()

@tool('get_balance_sheet',args_schema=StockInput, description='A function that returns the balance sheet based on a ticker symbol.')
def get_balance_sheet(ticker: str):
    print('get_balance_sheet tool is being used')
    stock = yf.Ticker(ticker)
    return stock.balance_sheet


@tool('get_stock_news',args_schema=StockInput, description='A function that returns news based on a ticker symbol.')
def get_stock_news(ticker: str):
    print('get_stock_news tool is being used')
    stock = yf.Ticker(ticker)
    return stock.news

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

