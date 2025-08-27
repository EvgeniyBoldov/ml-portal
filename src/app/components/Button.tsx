import React from "react";
import styles from "./Button.module.css";

type Props = React.ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: "primary" | "outline";
    size?: "md" | "sm";
    block?: boolean;
};
export default function Button({ variant="primary", size="md", block=false, className, ...props }: Props) {
    const cls = [
        styles.btn,
        variant === "primary" ? styles.primary : styles.outline,
        size === "sm" ? styles.sm : "",
        block ? styles.block : "",
        className ?? ""
    ].join(" ");
    return <button className={cls} {...props} />;
}
