import { useEffect, useState } from "react";
import { getServices } from "../lib/api.ts";
import s from "./Root.module.css";

type Svc = { name: string; url: string };

export default function Root() {
    const [services, setServices] = useState<Svc[]>([]);
    useEffect(() => { getServices().then(setServices).catch(() => setServices([])); }, []);

    return (
        <div className={s.wrap}>
            <div className={s.container}>
                <h1 className={s.title}>ML Cluster</h1>
                <div className={s.grid}>
                    {services.map(svc => (
                        <a key={svc.name} href={svc.url} className={s.card}>
                            <div className={s.cardName}>{svc.name}</div>
                            <div className={s.cardUrl}>{svc.url}</div>
                        </a>
                    ))}
                </div>
            </div>
        </div>
    );
}
