from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from passlib.context import CryptContext
from jose import jwt, JWTError
from bson import ObjectId
from datetime import datetime, timedelta

from database import users_collection, expenses_collection

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SECRET_KEY = "expense_secret_key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

security = HTTPBearer()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class User(BaseModel):
    username: str
    password: str


class Expense(BaseModel):
    title: str
    amount: float
    category: str


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")

        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")

        return username

    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


@app.get("/")
def home():
    return {"message": "Expense Tracker API Running"}


@app.post("/signup")
def signup(user: User):
    existing_user = users_collection.find_one({"username": user.username})

    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")

    hashed_password = pwd_context.hash(user.password)

    users_collection.insert_one({
        "username": user.username,
        "password": hashed_password
    })

    return {"message": "Signup successful"}


@app.post("/login")
def login(user: User):
    found_user = users_collection.find_one({"username": user.username})

    if not found_user:
        raise HTTPException(status_code=400, detail="User not found")

    if not pwd_context.verify(user.password, found_user["password"]):
        raise HTTPException(status_code=400, detail="Incorrect password")

    token = create_access_token({"sub": user.username})

    return {
        "message": "Login successful",
        "access_token": token,
        "token_type": "bearer"
    }


@app.post("/add-expense")
def add_expense(expense: Expense, current_user: str = Depends(get_current_user)):
    expense_data = expense.dict()
    expense_data["username"] = current_user
    expense_data["date"] = datetime.now().strftime("%Y-%m-%d")

    expenses_collection.insert_one(expense_data)

    return {"message": "Expense added successfully"}


@app.get("/expenses")
def get_expenses(current_user: str = Depends(get_current_user)):
    data = []

    for expense in expenses_collection.find({"username": current_user}):
        expense["_id"] = str(expense["_id"])
        data.append(expense)

    return data


@app.put("/update-expense/{id}")
def update_expense(id: str, expense: Expense, current_user: str = Depends(get_current_user)):
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid expense ID")

    result = expenses_collection.update_one(
        {"_id": ObjectId(id), "username": current_user},
        {"$set": expense.dict()}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Expense not found")

    return {"message": "Expense updated successfully"}


@app.delete("/delete-expense/{id}")
def delete_expense(id: str, current_user: str = Depends(get_current_user)):
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid expense ID")

    result = expenses_collection.delete_one({
        "_id": ObjectId(id),
        "username": current_user
    })

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Expense not found")

    return {"message": "Expense deleted successfully"}


@app.get("/expense/{id}")
def get_single_expense(
    id: str,
    current_user: str = Depends(get_current_user)
):
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid expense Id")
    
    expense = expenses_collection.find_one({
        "_id": ObjectId(id),
        "username": current_user
    })

    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    
    expense["_id"] = str(expense["_id"])
    
    return expense



@app.get("/expenses/category/{category}")
def filter_by_category(category: str, current_user: str = Depends(get_current_user)):
    data = []

    for expense in expenses_collection.find({
        "username": current_user,
        "category": category
    }):
        expense["_id"] = str(expense["_id"])
        data.append(expense)

    return data


@app.get("/expenses/total")
def total_expenses(current_user: str = Depends(get_current_user)):
    total = 0

    for expense in expenses_collection.find({"username": current_user}):
        total += expense["amount"]

    return {"total_expenses": total}


@app.get("/top-category")
def top_category(current_user: str = Depends(get_current_user)):
    category_totals = {}

    for expense in expenses_collection.find({"username": current_user}):
        category = expense["category"]
        amount = expense["amount"]
        category_totals[category] = category_totals.get(category, 0) + amount

    if not category_totals:
        return {"message": "No expenses found"}

    top_cat = max(category_totals, key=category_totals.get)

    return {
        "top_category": top_cat,
        "amount": category_totals[top_cat]
    }

@app.get("/expenses/page/{page}")

def get_expenses_page(
    page: int,
    current_user: str = Depends(get_current_user)
):
    limit = 5
    skip = (page - 1) * limit
    expenses = []

    data = expenses_collection.find(
        {"username": current_user}
    ).skip(skip).limit(limit)

    for expense in data:
        expense["_id"] = str(expense["_id"])
        expenses.append(expense)

    return expenses

@app.get("/stats")
def get_stats(
    current_user: str = Depends(get_current_user)
):
    stats = {}

    for expense in expenses_collection.find(
        {"username": current_user}
    ):
        category = expense["category"]
        amount = expense["amount"]
        stats[category] = stats.get(category, 0) + amount

    return stats


@app.get("/monthly-summary/{month}")
def monthly_summary(month: str, current_user: str = Depends(get_current_user)):
    total = 0
    categories = {}

    for expense in expenses_collection.find({"username": current_user}):
        if str(expense["date"]).startswith(month):
            amount = expense["amount"]
            category = expense["category"]

            total += amount
            categories[category] = categories.get(category, 0) + amount

    return {
        "month": month,
        "total": total,
        "categories": categories
    }

@app.get("/chart-data")
def chart_data(current_user: str = Depends(get_current_user)):

    categories = {}

    for expense in expenses_collection.find(
        {"username": current_user}
    ):
        category = expense["category"]
        amount = expense["amount"]
        categories[category] = categories.get(category, 0) + amount

    return categories

@app.get("/all-expenses")
def get_all_expenses(
    current_user: str = Depends(get_current_user)
):
    expenses = []

    for expense in expenses_collection.find(
        {"username": current_user}
    ):
        expense["_id"] = str(expense["_id"])
        expenses.append(expense)
    
    return expenses