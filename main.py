from fastapi import FastAPI, Header, HTTPException, Depends # type: ignore
from pydantic import BaseModel # type: ignore
from typing import Optional
import os
from dotenv import load_dotenv # type: ignore
import jwt  # type: ignore # PyJWT
import psycopg2 # type: ignore
from fastapi.middleware.cors import CORSMiddleware # type: ignore
from jose import jwt as jose_jwt, jwk # type: ignore
from jose.utils import base64url_decode # type: ignore

app = FastAPI()

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000","http://localhost:5173","https://solarsarthi.netlify.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

load_dotenv()
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")
DATABASE_URL = os.getenv("DATABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

print("SUPABASE_JWT_SECRET:", SUPABASE_JWT_SECRET)
print("DATABASE_URL:", DATABASE_URL)
print("SUPABASE_ANON_KEY:", SUPABASE_ANON_KEY)

class UserProfile(BaseModel):
    firstName: str
    lastName: str
    mobileNumber: str
    password: Optional[str] = ""  # Making password optional for social logins


def get_current_user(authorization: Optional[str] = Header(None)):
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")

    token = authorization.split(" ")[1]

    try:
        payload = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )

        print("Decoded token payload:", payload)

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token payload")

        return user_id

    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Token verification failed: {str(e)}")


@app.post("/api/save-user")
def save_user(profile: UserProfile, user_id: str = Depends(get_current_user)):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        # First try to update existing user
        cursor.execute("""
            UPDATE profiles 
            SET first_name = %s, last_name = %s, number = %s
            WHERE id = %s
            RETURNING id
        """, (profile.firstName, profile.lastName, profile.mobileNumber, user_id))
        
        updated = cursor.fetchone()
        
        if not updated:
            # If no rows were updated, try to insert
            try:
                cursor.execute("""
                    INSERT INTO profiles (id, first_name, last_name, number, password, is_social_login)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    user_id, 
                    profile.firstName, 
                    profile.lastName, 
                    profile.mobileNumber,
                    profile.password if profile.password else None,
                    profile.password == ""
                ))
            except psycopg2.errors.UniqueViolation:
                # Handle case where another request already inserted the user
                conn.rollback()
                return {"message": "User already exists"}

        conn.commit()
        return {"message": "User saved successfully"}
        
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        cursor.close()
        conn.close()


# Endpoint to check if user exists and get profile info
@app.get("/api/user-profile")
def get_user_profile(user_id: str = Depends(get_current_user)):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT first_name, last_name, number, is_social_login
            FROM profiles WHERE id = %s
        """, (user_id,))
        
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")
            
        return {
            "firstName": user[0],
            "lastName": user[1],
            "mobileNumber": user[2],
            "isSocialLogin": user[3] if len(user) > 3 else False
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    

@app.post("/api/calculate-quote")
def calculate_quote(
    roof_area: float,
    electricity_bill: float,
    location: str,
    user_id: str = Depends(get_current_user)
):
    try:
        # Simple calculation - replace with your actual business logic
        system_size = min(roof_area / 100, electricity_bill / 1000)
        estimated_cost = system_size * 50000  # ₹50,000 per kW
        annual_savings = electricity_bill * 12 * 0.8  # 80% savings
        
        return {
            "system_size_kw": round(system_size, 2),
            "estimated_cost": round(estimated_cost, 2),
            "annual_savings": round(annual_savings, 2),
            "payback_period": round(estimated_cost / annual_savings, 1)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))