export type ChatMessage = { role: "user"|"assistant"|"system"; content: string };

const USE_MOCKS = true;

export async function login(u: string, p: string) {
  if (u==="admin" && p==="admin") return { access_token: "mock-admin", token_type: "bearer" as const };
  if (u==="user"  && p==="user")  return { access_token: "mock-user",  token_type: "bearer" as const };
  throw new Error("Bad credentials");
}

export async function me(token: string) {
  if (token==="mock-admin") return { username: "admin", role: "admin" as const };
  if (token==="mock-user")  return { username: "user",  role: "user"  as const };
  throw new Error("Unauthorized");
}

export async function getServices() {
  return [
    { name: "GPT сервис", url: "/gpt" },
    { name: "Mlflow", url: "http://10.0.0.12:5000" },
    { name: "Jupyter", url: "http://10.0.0.34:8888" },
    { name: "Grafana", url: "http://10.0.0.56:3000" }
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
