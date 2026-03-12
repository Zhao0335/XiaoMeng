use serde::{Deserialize, Serialize};
use chrono::{DateTime, Utc};
use uuid::Uuid;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Source {
    Cli,
    Web,
    WebSocket,
    QQ,
    Telegram,
    Discord,
}

impl std::fmt::Display for Source {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Source::Cli => write!(f, "cli"),
            Source::Web => write!(f, "web"),
            Source::WebSocket => write!(f, "websocket"),
            Source::QQ => write!(f, "qq"),
            Source::Telegram => write!(f, "telegram"),
            Source::Discord => write!(f, "discord"),
        }
    }
}

impl std::str::FromStr for Source {
    type Err = String;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s.to_lowercase().as_str() {
            "cli" => Ok(Source::Cli),
            "web" => Ok(Source::Web),
            "websocket" => Ok(Source::WebSocket),
            "qq" => Ok(Source::QQ),
            "telegram" => Ok(Source::Telegram),
            "discord" => Ok(Source::Discord),
            _ => Err(format!("Unknown source: {}", s)),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "lowercase")]
pub enum UserLevel {
    #[default]
    Stranger,
    Whitelist,
    Owner,
}

impl std::fmt::Display for UserLevel {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            UserLevel::Owner => write!(f, "owner"),
            UserLevel::Whitelist => write!(f, "whitelist"),
            UserLevel::Stranger => write!(f, "stranger"),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct User {
    pub user_id: String,
    pub level: UserLevel,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub nickname: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub channel_user_id: Option<String>,
}

impl User {
    pub fn new(user_id: impl Into<String>, level: UserLevel) -> Self {
        Self {
            user_id: user_id.into(),
            level,
            nickname: None,
            channel_user_id: None,
        }
    }

    pub fn owner(user_id: impl Into<String>) -> Self {
        Self::new(user_id, UserLevel::Owner)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Message {
    pub id: String,
    pub source: Source,
    pub user: User,
    pub content: String,
    pub timestamp: DateTime<Utc>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reply_to: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub metadata: Option<serde_json::Value>,
}

impl Message {
    pub fn new(source: Source, user: User, content: impl Into<String>) -> Self {
        Self {
            id: Uuid::new_v4().to_string(),
            source,
            user,
            content: content.into(),
            timestamp: Utc::now(),
            reply_to: None,
            metadata: None,
        }
    }

    pub fn cli(user: User, content: impl Into<String>) -> Self {
        Self::new(Source::Cli, user, content)
    }

    pub fn web(user: User, content: impl Into<String>) -> Self {
        Self::new(Source::Web, user, content)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Response {
    pub message_id: String,
    pub content: String,
    pub timestamp: DateTime<Utc>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub metadata: Option<serde_json::Value>,
}

impl Response {
    pub fn new(message_id: impl Into<String>, content: impl Into<String>) -> Self {
        Self {
            message_id: message_id.into(),
            content: content.into(),
            timestamp: Utc::now(),
            metadata: None,
        }
    }

    pub fn simple(content: impl Into<String>) -> Self {
        Self::new(Uuid::new_v4().to_string(), content)
    }
}
