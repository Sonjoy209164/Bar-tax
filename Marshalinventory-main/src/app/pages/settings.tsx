import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Button } from "../components/ui/button";
import { Switch } from "../components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { Avatar, AvatarFallback } from "../components/ui/avatar";
import { Badge } from "../components/ui/badge";
import { User, Building2, Key, Palette, Bell } from "lucide-react";
import { motion } from "motion/react";

export function SettingsPage() {
  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="mb-1">Settings</h1>
        <p className="text-muted-foreground">
          Manage your account, workspace, and preferences
        </p>
      </div>

      <Tabs defaultValue="profile">
        <TabsList>
          <TabsTrigger value="profile">Profile</TabsTrigger>
          <TabsTrigger value="workspace">Workspace</TabsTrigger>
          <TabsTrigger value="integrations">Integrations</TabsTrigger>
          <TabsTrigger value="appearance">Appearance</TabsTrigger>
          <TabsTrigger value="notifications">Notifications</TabsTrigger>
        </TabsList>

        <TabsContent value="profile" className="mt-6 space-y-6">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
          >
            <Card>
              <CardHeader>
                <CardTitle>Profile Information</CardTitle>
                <CardDescription>Update your personal details</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="flex items-center gap-4">
                  <Avatar className="h-20 w-20">
                    <AvatarFallback className="bg-primary text-2xl text-primary-foreground">
                      SC
                    </AvatarFallback>
                  </Avatar>
                  <div>
                    <Button variant="outline" size="sm">Change Photo</Button>
                    <p className="mt-2 text-xs text-muted-foreground">
                      JPG, PNG or WebP. Max 2MB.
                    </p>
                  </div>
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="first-name">First Name</Label>
                    <Input id="first-name" defaultValue="Sarah" />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="last-name">Last Name</Label>
                    <Input id="last-name" defaultValue="Chen" />
                  </div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="email">Email</Label>
                  <Input id="email" type="email" defaultValue="sarah@inventrix.com" />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="role">Role</Label>
                  <Input id="role" defaultValue="Product Manager" />
                </div>
                <Button>Save Changes</Button>
              </CardContent>
            </Card>
          </motion.div>
        </TabsContent>

        <TabsContent value="workspace" className="mt-6 space-y-6">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
          >
            <Card>
              <CardHeader>
                <CardTitle>Workspace Settings</CardTitle>
                <CardDescription>Manage your workspace configuration</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="workspace-name">Workspace Name</Label>
                  <Input id="workspace-name" defaultValue="Inventrix Pro" />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="workspace-url">Workspace URL</Label>
                  <div className="flex gap-2">
                    <Input id="workspace-url" defaultValue="inventrix-pro" />
                    <span className="flex items-center text-sm text-muted-foreground">
                      .inventrix.app
                    </span>
                  </div>
                </div>
                <div className="space-y-2">
                  <Label>Team Members</Label>
                  <div className="space-y-2">
                    <div className="flex items-center justify-between rounded-lg border border-border p-3">
                      <div className="flex items-center gap-3">
                        <Avatar>
                          <AvatarFallback className="bg-primary text-primary-foreground">
                            SC
                          </AvatarFallback>
                        </Avatar>
                        <div>
                          <p className="font-medium">Sarah Chen</p>
                          <p className="text-sm text-muted-foreground">sarah@inventrix.com</p>
                        </div>
                      </div>
                      <Badge>Owner</Badge>
                    </div>
                    <div className="flex items-center justify-between rounded-lg border border-border p-3">
                      <div className="flex items-center gap-3">
                        <Avatar>
                          <AvatarFallback className="bg-accent">MJ</AvatarFallback>
                        </Avatar>
                        <div>
                          <p className="font-medium">Mike Johnson</p>
                          <p className="text-sm text-muted-foreground">mike@inventrix.com</p>
                        </div>
                      </div>
                      <Badge variant="secondary">Admin</Badge>
                    </div>
                  </div>
                </div>
                <Button variant="outline">Invite Team Member</Button>
              </CardContent>
            </Card>
          </motion.div>
        </TabsContent>

        <TabsContent value="integrations" className="mt-6 space-y-6">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
          >
            <Card>
              <CardHeader>
                <CardTitle>API Keys</CardTitle>
                <CardDescription>Manage your API keys and integrations</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="api-key">Production API Key</Label>
                  <div className="flex gap-2">
                    <Input
                      id="api-key"
                      type="password"
                      defaultValue="sk_live_1234567890abcdefghij"
                      readOnly
                    />
                    <Button variant="outline">Copy</Button>
                  </div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="webhook">Webhook URL</Label>
                  <Input id="webhook" placeholder="https://your-domain.com/webhook" />
                </div>
                <Button variant="outline">Generate New Key</Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>RAG Integration Status</CardTitle>
                <CardDescription>Monitor your AI assistant connection</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="h-2 w-2 rounded-full bg-green-500" />
                    <span className="text-sm font-medium">Connected</span>
                  </div>
                  <Badge variant="success">Active</Badge>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Endpoint</span>
                  <span className="font-mono">api.rag.inventrix.ai</span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Last Sync</span>
                  <span>2 hours ago</span>
                </div>
                <Button variant="outline" className="w-full">Test Connection</Button>
              </CardContent>
            </Card>
          </motion.div>
        </TabsContent>

        <TabsContent value="appearance" className="mt-6 space-y-6">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
          >
            <Card>
              <CardHeader>
                <CardTitle>Theme</CardTitle>
                <CardDescription>Customize your interface appearance</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-medium">Dark Mode</p>
                    <p className="text-sm text-muted-foreground">
                      Toggle between light and dark themes
                    </p>
                  </div>
                  <Switch />
                </div>
                <div className="grid grid-cols-2 gap-4 pt-4">
                  <button className="group relative overflow-hidden rounded-lg border-2 border-primary p-4 transition-all hover:shadow-lg">
                    <div className="mb-2 h-20 rounded-md bg-background" />
                    <div className="space-y-2">
                      <div className="h-2 rounded bg-muted" />
                      <div className="h-2 w-2/3 rounded bg-muted" />
                    </div>
                    <div className="absolute right-2 top-2">
                      <div className="rounded-full bg-primary p-1">
                        <svg className="h-3 w-3 text-primary-foreground" fill="currentColor" viewBox="0 0 20 20">
                          <path d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" />
                        </svg>
                      </div>
                    </div>
                    <p className="mt-2 text-sm font-medium">Light</p>
                  </button>
                  <button className="relative overflow-hidden rounded-lg border-2 border-border p-4 transition-all hover:border-primary hover:shadow-lg">
                    <div className="mb-2 h-20 rounded-md bg-gray-900" />
                    <div className="space-y-2">
                      <div className="h-2 rounded bg-gray-800" />
                      <div className="h-2 w-2/3 rounded bg-gray-800" />
                    </div>
                    <p className="mt-2 text-sm font-medium">Dark</p>
                  </button>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        </TabsContent>

        <TabsContent value="notifications" className="mt-6 space-y-6">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
          >
            <Card>
              <CardHeader>
                <CardTitle>Notification Preferences</CardTitle>
                <CardDescription>Choose what updates you want to receive</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div>
                  <h4 className="mb-4 text-sm font-medium">Email Notifications</h4>
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="font-medium">Low Stock Alerts</p>
                        <p className="text-sm text-muted-foreground">
                          Get notified when products run low
                        </p>
                      </div>
                      <Switch defaultChecked />
                    </div>
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="font-medium">RAG Sync Updates</p>
                        <p className="text-sm text-muted-foreground">
                          Notifications about AI indexing
                        </p>
                      </div>
                      <Switch defaultChecked />
                    </div>
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="font-medium">Export Completion</p>
                        <p className="text-sm text-muted-foreground">
                          When your exports are ready
                        </p>
                      </div>
                      <Switch defaultChecked />
                    </div>
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="font-medium">Team Activity</p>
                        <p className="text-sm text-muted-foreground">
                          Updates from team members
                        </p>
                      </div>
                      <Switch />
                    </div>
                  </div>
                </div>
                <Button>Save Preferences</Button>
              </CardContent>
            </Card>
          </motion.div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
