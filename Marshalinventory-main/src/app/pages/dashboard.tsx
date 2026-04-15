import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import {
  Package,
  TrendingDown,
  FolderOpen,
  Clock,
  Plus,
  Upload,
  Download,
  Database,
  ArrowUpRight,
  ArrowDownRight,
  Activity,
} from "lucide-react";
import { motion } from "motion/react";

const stats = [
  {
    title: "Total Products",
    value: "1,248",
    change: "+12.5%",
    trend: "up",
    icon: Package,
  },
  {
    title: "Low Stock Items",
    value: "23",
    change: "-8.2%",
    trend: "down",
    icon: TrendingDown,
  },
  {
    title: "Categories",
    value: "48",
    change: "+2",
    trend: "up",
    icon: FolderOpen,
  },
  {
    title: "Updated Today",
    value: "156",
    change: "+23.1%",
    trend: "up",
    icon: Clock,
  },
];

const recentActivity = [
  {
    action: "Product Added",
    product: "Wireless Headphones Pro",
    time: "2 minutes ago",
    user: "Sarah Chen",
  },
  {
    action: "Stock Updated",
    product: "Laptop Stand Aluminum",
    time: "15 minutes ago",
    user: "Mike Johnson",
  },
  {
    action: "RAG Sync Complete",
    product: "156 products indexed",
    time: "1 hour ago",
    user: "System",
  },
  {
    action: "Export Generated",
    product: "Product Catalog JSON",
    time: "2 hours ago",
    user: "Sarah Chen",
  },
  {
    action: "Low Stock Alert",
    product: "5 products below threshold",
    time: "3 hours ago",
    user: "System",
  },
];

export function DashboardPage() {
  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="mb-1">Dashboard</h1>
          <p className="text-muted-foreground">Welcome back! Here's your inventory overview</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm">
            <Upload className="mr-2 h-4 w-4" />
            Import
          </Button>
          <Button size="sm">
            <Plus className="mr-2 h-4 w-4" />
            Add Product
          </Button>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat, index) => (
          <motion.div
            key={stat.title}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.1, duration: 0.4 }}
          >
            <Card className="transition-shadow hover:shadow-md">
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  {stat.title}
                </CardTitle>
                <stat.icon className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold">{stat.value}</div>
                <div className="mt-2 flex items-center gap-1 text-xs">
                  {stat.trend === "up" ? (
                    <ArrowUpRight className="h-3 w-3 text-green-500" />
                  ) : (
                    <ArrowDownRight className="h-3 w-3 text-red-500" />
                  )}
                  <span
                    className={stat.trend === "up" ? "text-green-500" : "text-red-500"}
                  >
                    {stat.change}
                  </span>
                  <span className="text-muted-foreground">from last month</span>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.5, duration: 0.5 }}
          className="lg:col-span-2"
        >
          <Card>
            <CardHeader>
              <CardTitle>Recent Activity</CardTitle>
              <CardDescription>Track changes and updates to your inventory</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {recentActivity.map((activity, index) => (
                  <motion.div
                    key={index}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.6 + index * 0.05, duration: 0.3 }}
                    className="flex items-start gap-4 rounded-lg border border-border p-4 transition-colors hover:bg-accent/50"
                  >
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
                      <Activity className="h-5 w-5 text-primary" />
                    </div>
                    <div className="flex-1 space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{activity.action}</span>
                        {activity.user === "System" && (
                          <Badge variant="secondary" className="text-xs">
                            Auto
                          </Badge>
                        )}
                      </div>
                      <p className="text-sm text-muted-foreground">{activity.product}</p>
                      <p className="text-xs text-muted-foreground">{activity.time} by {activity.user}</p>
                    </div>
                  </motion.div>
                ))}
              </div>
            </CardContent>
          </Card>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.6, duration: 0.5 }}
          className="space-y-6"
        >
          <Card>
            <CardHeader>
              <CardTitle>Quick Actions</CardTitle>
              <CardDescription>Streamline your workflow</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              <Button variant="outline" className="w-full justify-start">
                <Plus className="mr-2 h-4 w-4" />
                Add Product
              </Button>
              <Button variant="outline" className="w-full justify-start">
                <Upload className="mr-2 h-4 w-4" />
                Import Products
              </Button>
              <Button variant="outline" className="w-full justify-start">
                <Download className="mr-2 h-4 w-4" />
                Export JSON
              </Button>
              <Button variant="outline" className="w-full justify-start">
                <Download className="mr-2 h-4 w-4" />
                Export DOC
              </Button>
              <Button variant="outline" className="w-full justify-start">
                <Database className="mr-2 h-4 w-4" />
                Sync to RAG
              </Button>
            </CardContent>
          </Card>

          <Card className="border-primary/50 bg-gradient-to-br from-primary/5 to-accent/5">
            <CardHeader>
              <CardTitle>Inventory Insights</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <div className="mb-2 flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Stock Level</span>
                  <span className="font-medium">78%</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-secondary">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: "78%" }}
                    transition={{ delay: 0.8, duration: 0.8 }}
                    className="h-full bg-primary"
                  />
                </div>
              </div>
              <div>
                <div className="mb-2 flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">RAG Coverage</span>
                  <span className="font-medium">94%</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-secondary">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: "94%" }}
                    transition={{ delay: 1, duration: 0.8 }}
                    className="h-full bg-accent"
                  />
                </div>
              </div>
              <div className="pt-2">
                <p className="text-sm text-muted-foreground">
                  Your inventory is well-stocked and optimized for AI queries
                </p>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      </div>
    </div>
  );
}
