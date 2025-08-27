import React from "react";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";

import AppShell from "./app/layout/AppShell.tsx";
import Root from "./app/routes/Root.tsx";
import GPTGate from "./app/routes/GPTGate.tsx";
import Chat from "./app/routes/gpt/Chat.tsx";
import Doc from "./app/routes/gpt/Doc.tsx";
import RagList from "./app/routes/gpt/admin/RagList.tsx";
import RagAdd from "./app/routes/gpt/admin/RagAdd.tsx";
import RagDelete from "./app/routes/gpt/admin/RagDelete.tsx";
import { ThemeProvider } from "./app/theme/ThemeProvider.tsx";

import "./index.css"; // тут импортируется theme.css внутри, как ты настроил

const router = createBrowserRouter([
    {
        path: "/",
        element: <AppShell />,      // хедер всегда сверху
        children: [
            { index: true, element: <Root /> },  // плитка
            {
                path: "gpt",
                element: <GPTGate />,   // если нет токена → Login, иначе GPTLayout
                children: [
                    { index: true, element: <Chat /> },
                    { path: "chat", element: <Chat /> },
                    { path: "doc", element: <Doc /> },
                    { path: "admin/list", element: <RagList /> },
                    { path: "admin/add", element: <RagAdd /> },
                    { path: "admin/delete", element: <RagDelete /> },
                ],
            },
            // при желании можешь оставить /login отдельным путём:
            // { path: "login", element: <Login /> },
        ],
    },
]);

ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
        <ThemeProvider>
            <RouterProvider router={router} />
        </ThemeProvider>
    </React.StrictMode>
);
