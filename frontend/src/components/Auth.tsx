import { useState, useEffect } from "react";

interface User {
  username: string;
  role: string;
}

interface AuthProps {
  token: string | null;
  setToken: (token: string | null) => void;
}

export default function Auth({ token, setToken }: AuthProps) {
  const [isLogin, setIsLogin] = useState(true);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [message, setMessage] = useState<{
    text: string;
    isError: boolean;
  } | null>(null);

  useEffect(() => {
    if (!token) {
      setCurrentUser(null);
      return;
    }

    fetch("/api/auth/me", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => {
        if (!res.ok) throw new Error("Érvénytelen token");
        return res.json();
      })
      .then((data: User) => setCurrentUser(data))
      .catch(() => {
        localStorage.removeItem("token");
        setToken(null);
      });
  }, [token, setToken]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setMessage(null);

    if (isLogin) {
      // OAuth2PasswordRequestForm x-www-form-urlencoded formátumot vár
      const body = new URLSearchParams();
      body.append("username", username);
      body.append("password", password);

      try {
        const res = await fetch("/api/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: body.toString(),
        });
        const data = await res.json();
        if (!res.ok)
          throw new Error(data.detail || "Incorrect username or password");

        localStorage.setItem("token", data.access_token);
        setToken(data.access_token);
        setUsername("");
        setPassword("");
      } catch (err: unknown) {
        setMessage({
          text: err instanceof Error ? err.message : "Error",
          isError: true,
        });
      }
    } else {
      try {
        const res = await fetch("/api/auth/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username, password, role: "engineer" }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Failed Registration");

        setIsLogin(true);
        setMessage({
          text: "Successful registration, login.",
          isError: false,
        });
        setPassword("");
      } catch (err: unknown) {
        setMessage({
          text: err instanceof Error ? err.message : "Error",
          isError: true,
        });
      }
    }
  };

  const handleLogout = () => {
    localStorage.removeItem("token");
    setToken(null);
  };

  if (currentUser) {
    return (
      <div>
        <span>
          Logged in: <strong>{currentUser.username}</strong> ({currentUser.role}
          )
        </span>
        <button type="button" onClick={handleLogout}>
          Logout
        </button>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: "420px", margin: "2rem auto", textAlign: "left" }}>
      <h4 style={{ margin: 0 }}>{isLogin ? "Login" : "Registration"}</h4>
      {message && (
        <p
          style={{
            color: message.isError ? "var(--pico-color-red-500)" : "inherit",
          }}
        >
          {message.text}
        </p>
      )}
      <article>
        <form onSubmit={handleSubmit}>
          <input
            type="text"
            placeholder="Username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
          />
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          <button type="submit">{isLogin ? "Login" : "Registration"}</button>
          <button
            type="button"
            onClick={() => {
              setIsLogin(!isLogin);
              setMessage(null);
            }}
          >
            {isLogin ? "I don't have an account" : "Back to login."}
          </button>
        </form>
      </article>
    </div>
  );
}
