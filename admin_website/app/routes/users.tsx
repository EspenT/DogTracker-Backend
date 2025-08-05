import type { Route } from "./+types/users";
import type { AuthContextType} from "../contexts/auth-context";
import RowViewer from "../components/row-viewer";

export async function loader({ params, request }: Route.LoaderArgs) {
    return {};
}

async function fetchUsers(authContext: AuthContextType): Promise<Record<string, string>[]> {
    return await fetch(`http://localhost:8000/admin/users`, {
      headers: authContext.getAuthHeaders(),
    }).then(response => {
        if (!response.ok) {
          throw new Error(`Failed to fetch users: ${response.status}`);
        }
        return response.json();
    });
}

export async function clientLoader({ serverLoader }: Route.ClientLoaderArgs) {
  const serverData = await serverLoader();
  return serverData;
}

export default function Component({ loaderData }: Route.ComponentProps) {
  return RowViewer(fetchUsers);
}
