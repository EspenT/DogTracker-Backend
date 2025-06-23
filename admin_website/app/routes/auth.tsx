import { redirect } from "react-router";
import type { Route } from "./+types/auth";
import { getSession, commitSession, destroySession } from "../sessions.server";

export async function loader({ request }: Route.LoaderArgs) {
  const session = await getSession(request.headers.get("Cookie"));
  const token = session.get("token");
  
  return {
    token: token || null,
  };
}

export async function action({ request }: Route.ActionArgs) {
  const session = await getSession(request.headers.get("Cookie"));
  const formData = await request.formData();
  const action = formData.get("action");

  if (action === "login") {
    const token = formData.get("token");
    if (typeof token === "string") {
      session.set("token", token);
      return redirect("/", {
        headers: {
          "Set-Cookie": await commitSession(session),
        },
      });
    }
  }

  if (action === "logout") {
    return redirect("/login", {
      headers: {
        "Set-Cookie": await destroySession(session),
      },
    });
  }

  return null;
}

// This component should never render as it's only used for actions
export default function AuthRoute() {
  return null;
}
