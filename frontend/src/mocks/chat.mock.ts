export async function mockLogin(username: string, password: string) {
  // demo: admin/admin → role=admin; user/user → role=user
  if (username==="admin" && password==="admin") return { access_token: "mock-admin", token_type: "bearer" as const };
  if (username==="user" && password==="user") return { access_token: "mock-user",  token_type: "bearer" as const };
  throw new Error("Bad credentials");
}

export async function mockMe(token: string) {
  if (token==="mock-admin") return { username: "admin", role: "admin" as const };
  if (token==="mock-user")  return { username: "user",  role: "user"  as const };
  throw new Error("Unauthorized");
}

export async function mockServices() {
  return [
    { name: "GPT сервис", url: "/gpt" },
    { name: "Mlflow", url: "http://10.0.0.12:5000" },
    { name: "Jupyter", url: "http://10.0.0.34:8888" },
    { name: "Grafana", url: "http://10.0.0.56:3000" }
  ];
}

export async function* mockChatStream({ messages }:{ messages: {content:string}[] }) {
  const last = messages.at(-1)?.content || "";
  const answer = `Ответ (mock): ${last}`;
  const tokens = answer.split(" ");
  for (const t of tokens) {
    await new Promise(r=>setTimeout(r, 40));
    yield t + " ";
  }
}
