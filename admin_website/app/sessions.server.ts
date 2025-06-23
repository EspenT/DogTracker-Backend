import { createCookieSessionStorage } from "react-router";

type SessionData = {
  token: string;
};

type SessionFlashData = {
  error: string;
};


const cookieMaxAgeInDays = 7;
const cookieMaxAgeInSeconds = 60 * 60 * 24 * cookieMaxAgeInDays;

const { getSession, commitSession, destroySession } =
  createCookieSessionStorage<SessionData, SessionFlashData>(
    {
      cookie: {
        name: "__session",
        httpOnly: true,
        maxAge: cookieMaxAgeInSeconds, 
        path: "/",
        sameSite: "lax",
        secure: true,
      },
    }
  );

export { getSession, commitSession, destroySession };
