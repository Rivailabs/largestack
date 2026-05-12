/**
 * LARGESTACK Agentic AI — TypeScript SDK
 * 
 * Usage:
 *   import { LargestackClient, Agent } from "@largestack-ai/sdk";
 *   
 *   const client = new LargestackClient({ baseUrl: "http://localhost:8787" });
 *   const result = await client.run("researcher", "Analyze AI trends");
 *   
 *   // Or use Agent class
 *   const agent = new Agent(client, "researcher");
 *   const result = await agent.run("What is machine learning?");
 *   for await (const token of agent.stream("Explain AI")) {
 *     process.stdout.write(token);
 *   }
 */

export interface LargestackConfig {
  baseUrl: string;
  apiKey?: string;
  timeout?: number;
}

export interface AgentResult {
  content: string;
  agent_name: string;
  total_cost: number;
  total_tokens: number;
  turns: number;
  trace_id: string;
  duration_ms: number;
  tool_calls_made: string[];
  status: string;
}

export interface RunOptions {
  session_id?: string;
  cost_budget?: number;
  max_turns?: number;
  images?: string[];
  response_model?: Record<string, any>;
}

export interface HealthStatus {
  status: string;
  version: string;
  timestamp: number;
}

export interface TraceRecord {
  trace_id: string;
  agent_name: string;
  task: string;
  duration_ms: number;
  cost: number;
  turns: number;
  timestamp: number;
}

export interface CostBreakdown {
  by_model: Array<{
    model: string;
    cost: number;
    calls: number;
  }>;
  period_days: number;
}

export class LargestackError extends Error {
  code: string;
  suggestion?: string;
  
  constructor(message: string, code: string, suggestion?: string) {
    super(message);
    this.name = "LargestackError";
    this.code = code;
    this.suggestion = suggestion;
  }
}

export class LargestackClient {
  private baseUrl: string;
  private apiKey?: string;
  private timeout: number;
  
  constructor(config: LargestackConfig) {
    this.baseUrl = config.baseUrl.replace(/\/$/, "");
    this.apiKey = config.apiKey;
    this.timeout = config.timeout || 300000; // 5 min default
  }
  
  private async fetch<T>(path: string, options: RequestInit = {}): Promise<T> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(options.headers as Record<string, string> || {}),
    };
    
    if (this.apiKey) {
      // v0.3.11: server expects `X-API-Key` (see largestack/serve.py L33).
      // Also set `Authorization: Bearer` for users running their own
      // gateway in front of LARGESTACK that uses standard bearer auth.
      headers["X-API-Key"] = this.apiKey;
      headers["Authorization"] = `Bearer ${this.apiKey}`;
    }
    
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);
    
    try {
      const response = await fetch(`${this.baseUrl}${path}`, {
        ...options,
        headers,
        signal: controller.signal,
      });
      
      if (!response.ok) {
        const error = await response.json().catch(() => ({})) as {
          detail?: string;
          code?: string;
          suggestion?: string;
        };
        throw new LargestackError(
          error.detail || `HTTP ${response.status}`,
          error.code || `HTTP_${response.status}`,
          error.suggestion,
        );
      }
      
      return await response.json() as T;
    } finally {
      clearTimeout(timeoutId);
    }
  }
  
  /** Run an agent with a task */
  async run(agentName: string, task: string, options?: RunOptions): Promise<AgentResult> {
    return this.fetch<AgentResult>("/run", {
      method: "POST",
      body: JSON.stringify({
        task,
        agent_name: agentName,
        ...options,
      }),
    });
  }
  
  /** Stream agent response as SSE */
  async *stream(agentName: string, task: string, options?: RunOptions): AsyncGenerator<string> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      "Accept": "text/event-stream",
    };
    if (this.apiKey) {
      // v0.3.11: server expects X-API-Key
      headers["X-API-Key"] = this.apiKey;
      headers["Authorization"] = `Bearer ${this.apiKey}`;
    }
    
    const response = await fetch(`${this.baseUrl}/stream`, {
      method: "POST",
      headers,
      body: JSON.stringify({ task, agent_name: agentName, ...options }),
    });
    
    if (!response.ok || !response.body) {
      throw new LargestackError("Stream failed", "STREAM_ERROR");
    }
    
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      
      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const data = line.slice(6);
          if (data === "[DONE]") return;
          try {
            const parsed = JSON.parse(data);
            if (parsed.token) yield parsed.token;
          } catch {
            yield data;
          }
        }
      }
    }
  }
  
  /** Check API health */
  async health(): Promise<HealthStatus> {
    return this.fetch<HealthStatus>("/api/health");
  }
  
  /** Get recent traces */
  async traces(limit: number = 100): Promise<{ traces: TraceRecord[] }> {
    return this.fetch(`/api/traces?limit=${limit}`);
  }
  
  /** Get cost breakdown */
  async costs(days: number = 7): Promise<CostBreakdown> {
    return this.fetch(`/api/costs?days=${days}`);
  }
  
  /** Get latency metrics */
  async metrics(): Promise<Record<string, number>> {
    return this.fetch("/api/metrics");
  }
  
  /** Get active alerts */
  async alerts(): Promise<{ alerts: Array<{ level: string; message: string }> }> {
    return this.fetch("/api/alerts");
  }
}

/** Agent wrapper for cleaner API */
export class Agent {
  private client: LargestackClient;
  name: string;
  
  constructor(client: LargestackClient, name: string) {
    this.client = client;
    this.name = name;
  }
  
  async run(task: string, options?: RunOptions): Promise<AgentResult> {
    return this.client.run(this.name, task, options);
  }
  
  async *stream(task: string, options?: RunOptions): AsyncGenerator<string> {
    yield* this.client.stream(this.name, task, options);
  }
}

// Default export for convenience
export default LargestackClient;
