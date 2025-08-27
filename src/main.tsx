import React from "react";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import Root from "./app/routes/Root";
import Login from "./app/routes/Login";
import GPTLayout from "./app/routes/gpt/GPTLayout";
import Chat from "./app/routes/gpt/Chat";
import Doc from "./app/routes/gpt/Doc";
import RagList from "./app/routes/gpt/admin/RagList";
import RagAdd from "./app/routes/gpt/admin/RagAdd";
import RagDelete from "./app/routes/gpt/admin/RagDelete";
import { ThemeProvider } from "./app/theme/ThemeProvider";
import "./index.css";

const router = createBrowserRouter([
    { path: "/", element: <Root /> },
    { path: "/login", element: <Login /> },
    {
        path: "/gpt",
        element: <GPTLayout />,
        children: [
            { index: true, element: <Chat /> },
            { path: "chat", element: <Chat /> },
            { path: "doc", element: <Doc /> },
            { path: "admin/list", element: <RagList /> },
            { path: "admin/add", element: <RagAdd /> },
            { path: "admin/delete", element: <RagDelete /> },
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
