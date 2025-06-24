
import { useState, useEffect } from "react";
import type { Route } from "./+types/users";
import type { AuthContextType} from "../contexts/auth-context";
import {useAuth} from "../contexts/auth-context";

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

interface UserViewerState  {
  refreshing: boolean;
  users: Record<string, string>[];
  clientError: string | null;
}

export default function Component({ loaderData }: Route.ComponentProps) {
  const authContext = useAuth();
  const [state, setState] = useState<UserViewerState>({
    refreshing: false,
    users: new Array<Record<string, string>>(),
    clientError: null,
  });

  const refreshUsers = async () => {
    setState(prev => ({ ...prev, refreshing: true, clientError: null }));
   
    await fetchUsers(authContext)
        .then(users => {
            setState(prev => ({
              ...prev,
              users: users,
              clientError: "",
              refreshing: false,
            }));
        })
        .catch(error => {
            setState(prev => ({
              ...prev,
              clientError: error instanceof Error ? "Unknown error" : error.message,
              refreshing: false,
            }));
        });
  }

  useEffect(() => {
      refreshUsers();
  }, []);

  const currentError = state.clientError;

  const formatUserRow = (user: string[], index: number) => {
    return (
      <tr key={index}>
        {user.map((col) => (<td>{col}</td>))}
      </tr>

    );
  };

  const userFields = state.users.length > 0 ? Object.keys(state.users[0]) : [];
  const userRows = () => {
      return state.users.map((user) => {
          return userFields.map(col => user[col]);
      });
  };
  return (
    <div className="h-screen flex flex-col bg-white">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-gray-800 mb-2">Users</h1>
        <div className="text-sm text-gray-600">
          <span className="mr-4">users: {state.users.length}</span>
        </div>
      </div>

      {/* Controls */}
      <div className="flex flex-wrap gap-3 mb-6 p-4 bg-gray-50 rounded-lg">
        <button
          onClick={refreshUsers}
          disabled={state.refreshing}
          className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:bg-blue-300 transition-colors flex items-center gap-2"
        >
          {state.refreshing ? (
            <>
              <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
              Refreshing...
            </>
          ) : (
            'Refresh'
          )}
        </button>
        
      </div>
      {/* Error Display */}
      {currentError && (
        <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg">
          <div className="flex items-center gap-2 text-red-800">
            <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
            </svg>
            <span className="font-semibold">Error loading users:</span>
          </div>
          <p className="text-red-700 mt-1">{currentError}</p>
        </div>
      )}

      <table className="table-auto text-sm text-black text-left ">
        <thead>
          <tr className="border-b">
            {userFields.map(col => <th>{col}</th>)}
          </tr>
        </thead>
        <tbody>
          {userRows().map((user, index) => formatUserRow(user, index))}
        </tbody>
      </table>
    </div>
  );
}
