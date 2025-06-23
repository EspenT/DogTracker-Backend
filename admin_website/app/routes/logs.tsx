import { useState, useEffect } from "react";
import type { Route } from "./+types/logs";
import type { AuthContextType} from "../contexts/auth-context";
import {useAuth} from "../contexts/auth-context";

export async function loader({ params, request }: Route.LoaderArgs) {
    return {};
}

async function fetchLogs(authContext: AuthContextType) {
    return await fetch(`http://localhost:8000/admin/logs`, {
      headers: authContext.getAuthHeaders(),
    }).then(response => {
        if (!response.ok) {
          throw new Error(`Failed to fetch logs: ${response.status}`);
        }
        return response.text();
    }).then(responseText => {
        return {
          logContent: responseText,
          timestamp: new Date().toLocaleString(),
          error: null
        };
    }).catch(error => {
        return {
          logContent: "",
          timestamp: new Date().toLocaleString(),
          error: error instanceof Error ? error.message : "Unknown error"
        };
    });
}

export async function clientLoader({ serverLoader }: Route.ClientLoaderArgs) {
  const serverData = await serverLoader();
  return serverData;
}

interface LogViewerState  {
  autoRefresh: boolean;
  refreshing: boolean;
  clientLogContent: string;
  clientError: string | null;
  lastLogUpdate: string;
}

export default function Component({ loaderData }: Route.ComponentProps) {
  const authContext = useAuth();
  const [state, setState] = useState<LogViewerState>({
    autoRefresh: false,
    refreshing: false,
    clientLogContent: "",
    clientError: null,
    lastLogUpdate: ""
  });

  const refreshLogs = async () => {
    setState(prev => ({ ...prev, refreshing: true, clientError: null }));
   
    const refreshResult = await fetchLogs(authContext);
    setState(prev => ({
      ...prev,
      clientLogContent: refreshResult instanceof Error ? "" : refreshResult.logContent,
      clientError: refreshResult.error,
      refreshing: false,
      lastLogUpdate: refreshResult.timestamp
    }));
  }

  useEffect(() => {
      fetchLogs(authContext).then((refreshResult) => {
        setState(prev => ({
          ...prev,
          clientLogContent: refreshResult instanceof Error ? "" : refreshResult.logContent,
          clientError: refreshResult.error,
          refreshing: false,
          lastLogUpdate: refreshResult.timestamp
        }));
      });
  }, []);

  useEffect(() => {
    let intervalId: NodeJS.Timeout;
    
    if (state.autoRefresh) {
      const refreshIntervalMs = 5000;
      intervalId = setInterval(refreshLogs, refreshIntervalMs);
    }
    
    return () => {
      if (intervalId) {
        clearInterval(intervalId);
      }
    };
  }, [state.autoRefresh]);

  const downloadLogs = () => {
    const blob = new Blob([state.clientLogContent], { type: 'text/plain' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `logs-${new Date().toISOString().split('T')[0]}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
  };

  const clearView = () => {
    setState(prev => ({ 
      ...prev, 
      clientLogContent: "", 
      clientError: null 
    }));
  };

  const formatLogLine = (line: string, index: number) => {
    let className = "font-mono text-sm whitespace-pre";
    
    if (line.includes('ERROR')) {
      className += " text-red-400";
    } else if (line.includes('WARN')) {
      className += " text-yellow-400";
    } else if (line.includes('INFO')) {
      className += " text-blue-400";
    } else if (line.includes('DEBUG')) {
      className += " text-gray-400";
    } else {
      className += " text-green-300";
    }
    
    return (
      <div key={index} className={`${className} px-3 py-0 hover:bg-gray-800`}>
        {line || '\u00A0'}
      </div>
    );
  };

  const currentError = state.clientError;
  const currentLogLines = state.clientLogContent.trim().split("\n");

  return (
    <div className="h-screen flex flex-col bg-white">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-gray-800 mb-2">Server Logs</h1>
        <div className="text-sm text-gray-600">
          <span className="mr-4">Last updated: {state.lastLogUpdate}</span>
          <span className="mr-4">Lines: {currentLogLines.length}</span>
        </div>
      </div>

      {/* Controls */}
      <div className="flex flex-wrap gap-3 mb-6 p-4 bg-gray-50 rounded-lg">
        <button
          onClick={refreshLogs}
          disabled={state.refreshing}
          className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:bg-blue-300 transition-colors flex items-center gap-2"
        >
          {state.refreshing ? (
            <>
              <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
              Refreshing...
            </>
          ) : (
            'Refresh Logs'
          )}
        </button>
        
        <button
          onClick={clearView}
          className="px-4 py-2 bg-gray-500 text-white rounded hover:bg-gray-600 transition-colors"
        >
          Clear View
        </button>
        
        <button
          onClick={downloadLogs}
          disabled={currentLogLines.length == 0}
          className="px-4 py-2 bg-green-500 text-white rounded hover:bg-green-600 disabled:bg-green-300 transition-colors"
        >
          Download Logs
        </button>
        
        <label className="flex items-center gap-2 px-3 py-2 bg-gray-500 rounded border">
          <input
            type="checkbox"
            checked={state.autoRefresh}
            onChange={(e) => setState(prev => ({ ...prev, autoRefresh: e.target.checked }))}
            className="rounded"
          />
          <span className="text-sm font-medium">Auto-refresh (5s)</span>
        </label>
      </div>

      {/* Error Display */}
      {currentError && (
        <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg">
          <div className="flex items-center gap-2 text-red-800">
            <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
            </svg>
            <span className="font-semibold">Error loading logs:</span>
          </div>
          <p className="text-red-700 mt-1">{currentError}</p>
        </div>
      )}

      {/* Log Content */}
      <div className="bg-gray-900 rounded-lg overflow-hidden">
        <div className="bg-gray-800 px-4 py-2 text-white text-sm font-medium flex justify-between items-center">
          <span>Log Output</span>
          <span className="text-gray-300">{currentLogLines.length} lines</span>
        </div>
        
        <div className="h-96 overflow-auto bg-black">
          {currentLogLines.length > 0 ? (
            <div className="p-0">
              {currentLogLines.map((line, index) => formatLogLine(line, index))}
            </div>
          ) : (
            <div className="flex items-center justify-center h-full text-gray-400">
              {state.refreshing ? (
                <div className="flex items-center gap-2">
                  <div className="w-6 h-6 border-2 border-gray-600 border-t-green-400 rounded-full animate-spin"></div>
                  Loading logs...
                </div>
              ) : (
                <div className="text-center">
                  <p className="mb-2">No log content available</p>
                  <button
                    onClick={refreshLogs}
                    className="text-green-400 hover:text-green-300 underline"
                  >
                    Try refreshing
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Footer Stats */}
      <div className="mt-4 text-xs text-gray-500 flex justify-between items-center">
        <span>
          Server rendered: {state.lastLogUpdate}
        </span>
        <span>
          {state.autoRefresh && (
            <span className="flex items-center gap-1">
              <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
              Auto-refreshing
            </span>
          )}
        </span>
      </div>
    </div>
  );
}
