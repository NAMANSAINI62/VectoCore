```mermaid
%%{init: {'theme':'base','themeVariables':{'background':'#111214','primaryColor':'#102b4a','primaryTextColor':'#e6f0ff','primaryBorderColor':'#3d6f9f','lineColor':'#9aa4b2','clusterBkg':'#16181c','clusterBorder':'#2a2e35','fontSize':'15px'}}}%%
flowchart LR
  subgraph USER[User and browser]
    User([User])
  end
  subgraph FE[Frontend]
    Forms[Register and login]
    AuthClient[Auth service]
    ApiClient[API client]
    Proxy[Next.js proxy]
  end
  subgraph API[Backend API]
    AuthAPI[Auth endpoints]
    Service[Auth service]
    Security[Token security]
    Repos[User and session repos]
  end
  subgraph DB[Storage]
    Postgres[(PostgreSQL)]
  end

  User -->|1. submit| Forms
  Forms -->|2. register or login| AuthClient
  AuthClient -->|3. POST auth| ApiClient
  ApiClient -->|4. credentials included| Proxy
  Proxy -->|5. forward request| AuthAPI
  AuthAPI -->|6. authenticate account| Service
  Service -->|7. hash/verify| Security
  Service -->|8. save user/session| Repos
  Repos -->|9. SQL records| Postgres
  AuthAPI -->|10. cookie response| Proxy
  Proxy -->|11. forward headers| ApiClient
  ApiClient -->|12. result| Forms

  classDef user fill:#172b3c,stroke:#7b8794,color:#f1f5f9;
  classDef frontend fill:#12365a,stroke:#4b91d1,color:#e6f0ff,stroke-width:2px;
  classDef backend fill:#163d63,stroke:#4b91d1,color:#e6f0ff,stroke-width:2px;
  classDef storage fill:#12365a,stroke:#4b91d1,color:#e6f0ff,stroke-width:2px;
  class User user;
  class Forms,AuthClient,ApiClient,Proxy frontend;
  class AuthAPI,Service,Security,Repos backend;
  class Postgres storage;
  %% Legend: solid = normal calls; dashed = conditional; blue = application/storage; gray = user; amber = decision.
```
Caption: Registration creates a user; login verifies the password, creates a session, then returns token data and HttpOnly cookies.
- Notice: Passwords are Argon2id-hashed; refresh tokens are stored as hashes.
- Notice: The browser API client includes credentials; the Next.js proxy forwards backend response headers.

```mermaid
%%{init: {'theme':'base','themeVariables':{'background':'#111214','primaryColor':'#102b4a','primaryTextColor':'#e6f0ff','primaryBorderColor':'#3d6f9f','lineColor':'#9aa4b2','clusterBkg':'#16181c','clusterBorder':'#2a2e35','fontSize':'15px'}}}%%
flowchart LR
  subgraph FE[Frontend]
    Browser([Browser])
    AuthClient[Auth service]
    ApiClient[API client]
    Proxy[Next.js proxy]
  end
  subgraph API[Backend API]
    AuthAPI[Auth endpoints]
    Service[Auth service]
    Security[Token security]
    Replay{Token reused?}
    Sessions[Session repository]
  end
  subgraph DB[Storage]
    Postgres[(PostgreSQL)]
  end

  Browser -->|1. session action| AuthClient
  AuthClient -->|2. POST auth| ApiClient
  ApiClient -->|3. send cookies| Proxy
  Proxy -->|4. forward request| AuthAPI
  AuthAPI -->|5. handle session| Service
  Service -->|6. hash token| Security
  Security -->|7. token hash| Service
  Service -->|8. lookup token| Sessions
  Sessions -->|9. query session| Postgres
  Postgres -->|10. session row| Sessions
  Sessions -->|11. return record| Service
  Service -->|12. check reuse| Replay
  Replay -->|13. replay revoke| Sessions
  Replay -->|14. valid continue| Service
  Service -->|15. issue tokens| Security
  Security -->|16. token pair| Service
  Service -->|17. save or revoke| Sessions
  Sessions -->|18. persist session| Postgres
  Service -->|19. token result| AuthAPI
  AuthAPI -->|20. cookie update| Proxy
  Proxy -->|21. response| Browser

  classDef user fill:#172b3c,stroke:#7b8794,color:#f1f5f9;
  classDef frontend fill:#12365a,stroke:#4b91d1,color:#e6f0ff,stroke-width:2px;
  classDef backend fill:#163d63,stroke:#4b91d1,color:#e6f0ff,stroke-width:2px;
  classDef decision fill:#563c14,stroke:#d9a441,color:#fff7df,stroke-width:2px;
  classDef storage fill:#12365a,stroke:#4b91d1,color:#e6f0ff,stroke-width:2px;
  class Browser user;
  class AuthClient,ApiClient,Proxy frontend;
  class AuthAPI,Service,Security,Sessions backend;
  class Replay decision;
  class Postgres storage;
  %% Legend: solid = normal calls; dashed = conditional; blue = application/storage; gray = user; amber = decision.
```
Caption: Refresh rotates a session token; reuse of a revoked token revokes its token family. Logout revokes the presented session.
- Notice: Refresh and access tokens travel in HttpOnly cookies; the refresh cookie is path-scoped.
- Notice: A reused token triggers family revocation; an expired token is revoked and rejected.

```mermaid
%%{init: {'theme':'base','themeVariables':{'background':'#111214','primaryColor':'#102b4a','primaryTextColor':'#e6f0ff','primaryBorderColor':'#3d6f9f','lineColor':'#9aa4b2','clusterBkg':'#16181c','clusterBorder':'#2a2e35','fontSize':'15px'}}}%%
flowchart LR
  subgraph FE[Frontend]
    Browser([Browser])
    Provider[Auth state provider]
    AuthClient[Auth service]
    ApiClient[API client]
    Proxy[Next.js proxy]
  end
  subgraph API[Backend API]
    Me[Current-user endpoint]
    Dependency[Auth dependency]
    Security[Token security]
    Users[User repository]
  end
  subgraph DB[Storage]
    Postgres[(PostgreSQL)]
  end

  Browser -->|1. load application| Provider
  Provider -->|2. request current user| AuthClient
  AuthClient -->|3. GET me| ApiClient
  ApiClient -->|4. include cookies| Proxy
  Proxy -->|5. forward request| Me
  Me -->|6. require identity| Dependency
  Dependency -->|7. decode access token| Security
  Dependency -->|8. load active user| Users
  Users -->|9. query by id| Postgres
  Users -->|10. return identity| Dependency
  Dependency -->|11. authenticated user| Me
  Me -->|12. response| Proxy
  Proxy -->|13. forward response| Provider

  classDef user fill:#172b3c,stroke:#7b8794,color:#f1f5f9;
  classDef frontend fill:#12365a,stroke:#4b91d1,color:#e6f0ff,stroke-width:2px;
  classDef backend fill:#163d63,stroke:#4b91d1,color:#e6f0ff,stroke-width:2px;
  classDef storage fill:#12365a,stroke:#4b91d1,color:#e6f0ff,stroke-width:2px;
  class Browser user;
  class Provider,AuthClient,ApiClient,Proxy frontend;
  class Me,Dependency,Security,Users backend;
  class Postgres storage;
  %% Legend: solid = normal calls; dashed = conditional; blue = application/storage; gray = user; amber = decision.
```
Caption: On application load, the auth provider calls `/api/v1/auth/me`; the backend validates the access token and loads the active user.
- Notice: Missing, invalid, expired, or inactive-user credentials are rejected by the auth dependency.
- Notice: The provider clears its local user state if the current-user request fails.

```mermaid
%%{init: {'theme':'base','themeVariables':{'background':'#111214','primaryColor':'#102b4a','primaryTextColor':'#e6f0ff','primaryBorderColor':'#3d6f9f','lineColor':'#9aa4b2','clusterBkg':'#16181c','clusterBorder':'#2a2e35','fontSize':'15px'}}}%%
flowchart LR
  subgraph FE[Frontend]
    LoginUI[Login OTP recovery view]
    AuthClient[Auth service]
    ApiClient[API client]
    Proxy[Next.js proxy]
  end
  subgraph API[Backend API]
    Endpoint[POST /password-otp/request]
    Service[Auth service]
    Known{Active user?}
    Security[OTP hash security]
    SMTP[Email service]
  end
  subgraph DB[Storage]
    Postgres[(PostgreSQL auth_otps)]
  end

  LoginUI -->|1. request reset OTP| AuthClient
  AuthClient -->|2. POST password-otp/request| ApiClient
  ApiClient -->|3. send request| Proxy
  Proxy -->|4. forward request| Endpoint
  Endpoint -->|5. prepare reset OTP| Service
  Service -->|6. check account| Known
  Known -->|7. yes: hash 6-digit OTP| Security
  Security -->|8. store hashed OTP| Postgres
  Service -.->|9. background task| SMTP
  Known -.->|7. no: skip silently| Endpoint
  Endpoint -->|10. generic response| Proxy
  Proxy -->|11. response| LoginUI

  classDef frontend fill:#12365a,stroke:#4b91d1,color:#e6f0ff,stroke-width:2px;
  classDef backend fill:#163d63,stroke:#4b91d1,color:#e6f0ff,stroke-width:2px;
  classDef decision fill:#563c14,stroke:#d9a441,color:#fff7df,stroke-width:2px;
  classDef storage fill:#12365a,stroke:#4b91d1,color:#e6f0ff,stroke-width:2px;
  class LoginUI,AuthClient,ApiClient,Proxy frontend;
  class Endpoint,Service,Security,SMTP backend;
  class Known decision;
  class Postgres storage;
  %% Legend: solid = normal calls; dashed = conditional; blue = application/storage; amber = decision.
```
Caption: Password reset requests via `/api/v1/auth/password-otp/request` return a generic confirmation to prevent account enumeration; active users get a hashed, expiring 6-digit OTP stored in `auth_otps` and emailed via FastAPI `BackgroundTasks`.
- Notice: Both passwordless sign-in (`/api/v1/auth/otp/*`) and password recovery (`/api/v1/auth/password-otp/*`) share the `auth_otps` table and SMTP delivery pipeline.
- Notice: Users trigger recovery directly from the `/login` screen without a separate legacy reset-link token table.

```mermaid
%%{init: {'theme':'base','themeVariables':{'background':'#111214','primaryColor':'#102b4a','primaryTextColor':'#e6f0ff','primaryBorderColor':'#3d6f9f','lineColor':'#9aa4b2','clusterBkg':'#16181c','clusterBorder':'#2a2e35','fontSize':'15px'}}}%%
flowchart LR
  subgraph FE[Frontend]
    LoginUI[Login OTP reset form]
    AuthClient[Auth service]
    ApiClient[API client]
    Proxy[Next.js proxy]
  end
  subgraph API[Backend API]
    Endpoint[POST /password-otp/reset]
    Service[Auth service]
    Valid{OTP valid and unexpired?}
    Security[Argon2id password hash]
    Sessions[Session repository]
  end
  subgraph DB[Storage]
    Postgres[(PostgreSQL)]
  end

  LoginUI -->|1. submit OTP + new password| AuthClient
  AuthClient -->|2. POST password-otp/reset| ApiClient
  ApiClient -->|3. send request| Proxy
  Proxy -->|4. forward request| Endpoint
  Endpoint -->|5. reset_password_with_otp| Service
  Service -->|6. verify and consume OTP| Postgres
  Postgres -->|7. OTP state| Valid
  Valid -->|8. yes: hash password| Security
  Security -->|9. update password_hash| Postgres
  Service -->|10. revoke all sessions| Sessions
  Sessions -->|11. revoke rows| Postgres
  Valid -.->|8. no: reject OTP| Endpoint
  Endpoint -->|12. response| Proxy
  Proxy -->|13. response| LoginUI

  classDef frontend fill:#12365a,stroke:#4b91d1,color:#e6f0ff,stroke-width:2px;
  classDef backend fill:#163d63,stroke:#4b91d1,color:#e6f0ff,stroke-width:2px;
  classDef decision fill:#563c14,stroke:#d9a441,color:#fff7df,stroke-width:2px;
  classDef storage fill:#12365a,stroke:#4b91d1,color:#e6f0ff,stroke-width:2px;
  class LoginUI,AuthClient,ApiClient,Proxy frontend;
  class Endpoint,Service,Security,Sessions backend;
  class Valid decision;
  class Postgres storage;
  %% Legend: solid = normal calls; dashed = conditional; blue = application/storage; amber = decision.
```
Caption: `/api/v1/auth/password-otp/reset` verifies and consumes the 6-digit OTP, Argon2id-hashes the new password, marks the user verified, and revokes every active refresh session for that user.
- Notice: Invalid, expired, or already-consumed OTPs are rejected.
- Notice: Password reset revokes all existing sessions via `session_repo.revoke_all_user_sessions(user.id)`.

Evidence
- `frontend/src/features/auth/login.tsx`
- `frontend/src/features/auth/register.tsx`
- `frontend/src/features/auth/AuthFormParts.tsx`
- `frontend/src/features/auth/provider.tsx`
- `frontend/src/features/auth/service.ts:11-66`
- `frontend/src/lib/apiClient.ts`
- `frontend/src/app/api/[...path]/route.ts`
- `frontend/src/app/login/page.tsx`
- `frontend/src/app/register/page.tsx`
- `backend/app/api/v1/router.py`
- `backend/app/main.py`
- `backend/app/api/v1/endpoints/auth.py:92-438`
- `backend/app/services/auth_service.py:1-325`
- `backend/app/services/email_service.py`
- `backend/app/core/security.py`
- `backend/app/dependencies/auth.py`
- `backend/app/repositories/user_repository.py`
- `backend/app/repositories/session_repository.py`
- `backend/app/models/user.py`
- `backend/app/models/user_session.py`
- `backend/app/models/auth_otp.py`
