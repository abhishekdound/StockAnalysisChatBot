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

