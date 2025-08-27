export type ChatMessage = { role: "user"|"assistant"|"system"; content: string };

const USE_MOCKS = true;

const BASE_URL = "http://localhost:8000";

type TokenResponse = { access_token: string; token_type: string };
type MeResponse = { username: string; role: string };

export async function login(username: string, password: string): Promise<TokenResponse> {
  const body = new URLSearchParams();
  body.append("username", username);
  body.append("password", password);

  const res = await fetch(`${BASE_URL}/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });

  if (!res.ok) {
    const txt = await res.text();
    throw new Error(txt || "Login failed");
  }
  return res.json();
}

export async function me(token: string): Promise<MeResponse> {
  const res = await fetch(`${BASE_URL}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(txt || "Me failed");
  }
  return res.json();
}

export async function getServices() {
  return [
    { name: "GPT сервис", url: "/gpt" },
    { name: "Mlflow", url: "http://10.69.106.202:5000" },
    { name: "Airflow", url: "http://10.69.106.202:8080" },
    { name: "Flower", url: "http://10.69.106.202:5555" },
    { name: "Jupyter", url: "http://10.69.106.200:8888" },
    { name: "Prefect", url: "http://10.69.106.202:4200" },
//     { name: "Grafana", url: "http://10.0.0.56:3000" }
  ];
}

export async function* chatStream({ messages }:{ messages: ChatMessage[] }) {
  const last = messages.at(-1)?.content ?? "";
  const answer = `Ответ (mock): ${last}`;
  for (const t of answer.split(" ")) {
    await new Promise(r => setTimeout(r, 35));
    yield t + " ";
  }
}
