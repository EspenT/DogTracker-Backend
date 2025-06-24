import { 
    route
} from "@react-router/dev/routes";
import type { RouteConfig } from "@react-router/dev/routes";

export default [
    route("login", "routes/login.tsx"),
    route("auth", "routes/auth.tsx"),
    route("", "routes/protected-layout.tsx", [
        route("logs", "routes/logs.tsx"),
        route("users", "routes/users.tsx"),
    ])
] satisfies RouteConfig;
