import { useState } from "react";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { Database, Download, RefreshCw, CheckCircle, AlertCircle, Clock } from "lucide-react";
import { motion } from "motion/react";

const syncHistory = [
  { id: 1, date: "2024-04-14 11:30 AM", products: 156, status: "success" },
  { id: 2, date: "2024-04-13 09:15 AM", products: 142, status: "success" },
  { id: 3, date: "2024-04-12 14:45 PM", products: 138, status: "success" },
  { id: 4, date: "2024-04-11 10:20 AM", products: 135, status: "failed" },
];

export function KnowledgeBasePage() {
  const [syncing, setSyncing] = useState(false);

  const handleSync = () => {
    setSyncing(true);
    setTimeout(() => setSyncing(false), 3000);
  };

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="mb-1">Knowledge Base</h1>
          <p className="text-muted-foreground">
            Manage RAG indexing and export your product data
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={handleSync} disabled={syncing}>
            <RefreshCw className={`mr-2 h-4 w-4 ${syncing ? "animate-spin" : ""}`} />
            {syncing ? "Syncing..." : "Sync to RAG"}
          </Button>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
        >
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Indexed Products
              </CardTitle>
              <Database className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold">1,248</div>
              <p className="mt-1 text-xs text-muted-foreground">
                94% of total inventory
              </p>
            </CardContent>
          </Card>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1, duration: 0.4 }}
        >
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Last Sync
              </CardTitle>
              <Clock className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold">2h ago</div>
              <p className="mt-1 text-xs text-muted-foreground">
                156 products updated
              </p>
            </CardContent>
          </Card>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2, duration: 0.4 }}
        >
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Sync Status
              </CardTitle>
              <CheckCircle className="h-4 w-4 text-green-500" />
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold">Healthy</div>
              <p className="mt-1 text-xs text-muted-foreground">
                All systems operational
              </p>
            </CardContent>
          </Card>
        </motion.div>
      </div>

      <Tabs defaultValue="export">
        <TabsList>
          <TabsTrigger value="export">Export Data</TabsTrigger>
          <TabsTrigger value="history">Sync History</TabsTrigger>
          <TabsTrigger value="settings">Settings</TabsTrigger>
        </TabsList>

        <TabsContent value="export" className="mt-6 space-y-6">
          <div className="grid gap-6 md:grid-cols-2">
            <motion.div
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.3, duration: 0.4 }}
            >
              <Card>
                <CardHeader>
                  <CardTitle>JSON Export</CardTitle>
                  <CardDescription>
                    Download your product catalog in JSON format
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="rounded-lg border border-border bg-muted p-4">
                    <pre className="text-xs text-muted-foreground overflow-x-auto">
                      {`{
  "products": [
    {
      "id": 1,
      "name": "Wireless...",
      "sku": "WHP-001",
      ...
    }
  ]
}`}
                    </pre>
                  </div>
                  <div className="space-y-2">
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">Total Products</span>
                      <span className="font-medium">1,248</span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">File Size</span>
                      <span className="font-medium">~2.4 MB</span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">Last Export</span>
                      <span className="font-medium">3 days ago</span>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button className="flex-1">
                      <Download className="mr-2 h-4 w-4" />
                      Download JSON
                    </Button>
                    <Button variant="outline">Copy</Button>
                  </div>
                </CardContent>
              </Card>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.4, duration: 0.4 }}
            >
              <Card>
                <CardHeader>
                  <CardTitle>Document Export</CardTitle>
                  <CardDescription>
                    Generate a formatted document of your catalog
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="rounded-lg border border-border bg-muted p-8 flex items-center justify-center">
                    <div className="text-center">
                      <div className="mx-auto mb-4 h-16 w-16 rounded-lg bg-background flex items-center justify-center">
                        <Download className="h-8 w-8 text-muted-foreground" />
                      </div>
                      <p className="text-sm text-muted-foreground">
                        Product Catalog Document
                      </p>
                    </div>
                  </div>
                  <div className="space-y-2">
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">Format</span>
                      <span className="font-medium">DOCX</span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">Pages</span>
                      <span className="font-medium">~125</span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">Last Export</span>
                      <span className="font-medium">1 week ago</span>
                    </div>
                  </div>
                  <Button className="w-full">
                    <Download className="mr-2 h-4 w-4" />
                    Generate Document
                  </Button>
                </CardContent>
              </Card>
            </motion.div>
          </div>
        </TabsContent>

        <TabsContent value="history" className="mt-6">
          <Card>
            <CardHeader>
              <CardTitle>Sync History</CardTitle>
              <CardDescription>View all RAG synchronization events</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {syncHistory.map((sync, index) => (
                  <motion.div
                    key={sync.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: index * 0.1, duration: 0.3 }}
                    className="flex items-center justify-between rounded-lg border border-border p-4"
                  >
                    <div className="flex items-center gap-4">
                      {sync.status === "success" ? (
                        <CheckCircle className="h-5 w-5 text-green-500" />
                      ) : (
                        <AlertCircle className="h-5 w-5 text-destructive" />
                      )}
                      <div>
                        <p className="font-medium">{sync.date}</p>
                        <p className="text-sm text-muted-foreground">
                          {sync.products} products synced
                        </p>
                      </div>
                    </div>
                    <Badge variant={sync.status === "success" ? "success" : "destructive"}>
                      {sync.status}
                    </Badge>
                  </motion.div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="settings" className="mt-6">
          <Card>
            <CardHeader>
              <CardTitle>RAG Configuration</CardTitle>
              <CardDescription>Manage your knowledge base settings</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-4">
                <div>
                  <h4 className="mb-2 text-sm font-medium">Auto-Sync Schedule</h4>
                  <p className="text-sm text-muted-foreground mb-3">
                    Automatically sync products to RAG on a schedule
                  </p>
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm">Every Hour</Button>
                    <Button variant="outline" size="sm">Every 6 Hours</Button>
                    <Button variant="default" size="sm">Daily</Button>
                    <Button variant="outline" size="sm">Manual</Button>
                  </div>
                </div>
                <div>
                  <h4 className="mb-2 text-sm font-medium">Include in Sync</h4>
                  <p className="text-sm text-muted-foreground mb-3">
                    Choose which product fields to index
                  </p>
                  <div className="space-y-2">
                    <label className="flex items-center gap-2">
                      <input type="checkbox" defaultChecked className="rounded" />
                      <span className="text-sm">Product descriptions</span>
                    </label>
                    <label className="flex items-center gap-2">
                      <input type="checkbox" defaultChecked className="rounded" />
                      <span className="text-sm">Tags and metadata</span>
                    </label>
                    <label className="flex items-center gap-2">
                      <input type="checkbox" defaultChecked className="rounded" />
                      <span className="text-sm">Stock and pricing</span>
                    </label>
                    <label className="flex items-center gap-2">
                      <input type="checkbox" className="rounded" />
                      <span className="text-sm">Product images</span>
                    </label>
                  </div>
                </div>
              </div>
              <Button>Save Settings</Button>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
